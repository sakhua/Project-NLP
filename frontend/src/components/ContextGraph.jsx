// Vẽ đồ thị bằng cytoscape. Dùng cho bảng "Đồ thị" của câu trả lời và trang Khám phá đồ thị.
import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";

export const EDGE_COLORS = {
  THAM_CHIEU: "#3451d1",
  THUOC: "#a3a39b",
  HUONG_DAN: "#1f8a4c",
  SUA_DOI: "#c26a05",
  BO_SUNG: "#c26a05",
  THAY_THE: "#c26a05",
  BAI_BO: "#c2362b",
  LIEN_QUAN: "#1f8a4c",        // GraphRAG kiểu Microsoft: quan hệ giữa hai thực thể
  XUAT_HIEN_TAI: "#a3a39b",    // thực thể → điều khoản nhắc tới nó
};

export const NODE_COLORS = {
  seed: "#3451d1",
  graph: "#e08a1e",
  path: "#c7c7c0",
  center: "#1c1c1a",
  entity: "#1f8a4c",
  entity_nb: "#9fd3b0",
  VanBan: "#1c1c1a",
  Chuong: "#55554f",
  Dieu: "#3451d1",
  Khoan: "#6d83e3",
  Diem: "#a9b6f0",
};

const STYLE = [
  {
    selector: "node",
    style: {
      "background-color": "data(color)",
      label: "data(label)",
      "font-size": 10,
      "font-family": "Segoe UI, Arial, sans-serif",
      color: "#33332f",
      "text-valign": "bottom",
      "text-margin-y": 5,
      "text-wrap": "wrap",
      "text-max-width": 110,
      "text-background-color": "#ffffff",
      "text-background-opacity": 0.85,
      "text-background-padding": 2,
      width: "data(size)",
      height: "data(size)",
      "border-width": 2,
      "border-color": "#ffffff",
    },
  },
  { selector: "node[?cited]", style: { "border-width": 4, "border-color": "#1c1c1a" } },
  { selector: "node[?focus]", style: { "border-width": 4, "border-color": "#1c1c1a", "font-weight": 700, "font-size": 11 } },
  { selector: "node:selected", style: { "border-width": 4, "border-color": "#1c1c1a", "overlay-opacity": 0 } },
  {
    selector: "edge",
    style: {
      width: 1.6,
      "line-color": "data(color)",
      "target-arrow-color": "data(color)",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.9,
      "curve-style": "bezier",
      label: "data(label)",
      "font-size": 8,
      color: "#77776f",
      "text-rotation": "autorotate",
      "text-background-color": "#ffffff",
      "text-background-opacity": 0.9,
      "text-background-padding": 1,
      opacity: 0.9,
    },
  },
  { selector: "edge[type = 'THUOC']", style: { "line-style": "dashed", label: "" } },
  { selector: "edge[type = 'XUAT_HIEN_TAI']", style: { "line-style": "dotted", label: "" } },
  { selector: "edge[type = 'LIEN_QUAN']", style: { "target-arrow-shape": "none" } },
  { selector: "node[shape]", style: { shape: "data(shape)" } },
  { selector: ".faded", style: { opacity: 0.18 } },
];

/**
 * elements: { nodes: [{id, label, color, size, cited?, focus?}], edges: [{source, target, type, label?}] }
 * onTap(id), onDblTap(id): sự kiện trên node. layout: "concentric" | "cose".
 */
export default function ContextGraph({ elements, onTap, onDblTap, layout = "cose", cyRef, className, edgeLabels = true, maxZoom = 1.3 }) {
  const box = useRef(null);
  const cy = useRef(null);
  const handlers = useRef({});
  handlers.current = { onTap, onDblTap };

  useEffect(() => {
    cy.current = cytoscape({ container: box.current, style: STYLE, minZoom: 0.25, maxZoom: 2.5, wheelSensitivity: 0.25 });
    cy.current.on("tap", "node", (e) => handlers.current.onTap?.(e.target.id()));
    cy.current.on("dbltap", "node", (e) => handlers.current.onDblTap?.(e.target.id()));
    cy.current.on("mouseover", "node", (e) => {
      const n = e.target;
      cy.current.elements().not(n.closedNeighborhood()).addClass("faded");
    });
    cy.current.on("mouseout", "node", () => cy.current.elements().removeClass("faded"));
    if (cyRef) cyRef.current = cy.current;
    const ro = new ResizeObserver(() => {   // khung đổi kích thước (bảng bên mở rộng): vẽ lại cho vừa
      const c = cy.current;
      if (!c) return;
      c.resize();
      if (c.nodes().length) { c.fit(undefined, 30); if (c.zoom() > maxZoom) { c.zoom(maxZoom); c.center(); } }
    });
    ro.observe(box.current);
    return () => { ro.disconnect(); cy.current.destroy(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const c = cy.current;
    if (!c || !elements) return;
    const nodes = elements.nodes.map((n) => ({ group: "nodes", data: { ...n } }));
    const ids = new Set(elements.nodes.map((n) => n.id));
    const edges = elements.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({
        group: "edges",
        data: { id: `${e.source}|${e.type}|${e.target}`, source: e.source, target: e.target, type: e.type,
          label: edgeLabels ? (e.label ?? e.type) : "", color: EDGE_COLORS[e.type] || "#a3a39b" },
      }));
    const prev = new Set(c.nodes().map((n) => n.id()));
    c.batch(() => {
      c.elements().forEach((el) => { if (!ids.has(el.id()) && el.isNode()) el.remove(); });
      for (const n of nodes) {
        const ex = c.getElementById(n.data.id);
        if (ex.length) ex.data(n.data); else c.add(n);
      }
      for (const e of edges) if (!c.getElementById(e.data.id).length) c.add(e);
    });
    const fresh = nodes.some((n) => !prev.has(n.data.id));
    if (fresh || prev.size === 0) {
      const opts = layout === "concentric"
        ? { name: "concentric", concentric: (n) => n.data("level") ?? 1, levelWidth: () => 1, minNodeSpacing: 46,
          animate: prev.size > 0, animationDuration: 350, padding: 30 }
        : { name: "cose", animate: prev.size > 0, animationDuration: 450, padding: 40, nodeRepulsion: () => 14000,
          idealEdgeLength: () => 100, nodeOverlap: 20, randomize: prev.size === 0 };
      const lay = c.layout(opts);
      lay.one("layoutstop", () => {   // ít node: không phóng quá to
        if (c.zoom() > maxZoom) { c.zoom(maxZoom); c.center(); }
      });
      lay.run();
    }
  }, [elements, layout, edgeLabels, maxZoom]);

  return <div ref={box} className={className || "canvas"} />;
}
