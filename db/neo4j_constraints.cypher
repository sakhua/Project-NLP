// Chạy một lần sau khi khởi động Neo4j (Neo4j Browser hoặc cypher-shell).
// Node chỉ lưu mã định danh; nội dung nằm trong PostgreSQL.
CREATE CONSTRAINT van_ban_id IF NOT EXISTS FOR (n:VanBan) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT chuong_id  IF NOT EXISTS FOR (n:Chuong) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT dieu_id    IF NOT EXISTS FOR (n:Dieu)   REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT khoan_id   IF NOT EXISTS FOR (n:Khoan)  REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT diem_id    IF NOT EXISTS FOR (n:Diem)   REQUIRE n.id IS UNIQUE;

// Các loại cạnh dùng trong đồ thị:
// (:Diem)-[:THUOC]->(:Khoan)-[:THUOC]->(:Dieu)-[:THUOC]->(:Chuong)-[:THUOC]->(:VanBan)
// (a)-[:THAM_CHIEU]->(b)
// (nghi_dinh)-[:HUONG_DAN]->(dieu_luat)
// (moi)-[:SUA_DOI|BO_SUNG|THAY_THE {ngay_hieu_luc: date}]->(cu)
// (moi)-[:BAI_BO {ngay_hieu_luc: date}]->(cu)
// (dieu_chuyen_tiep)-[:CHUYEN_TIEP]->(van_ban_sua_doi)
