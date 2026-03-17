-- Migration: Alter ai_audit_document_types - rename description to description_en, add description_th
-- Date: 2026-03-11
-- Description: Bilingual descriptions for document types

-- Rename description -> description_en
ALTER TABLE ai_audit_document_types RENAME COLUMN description TO description_en;

-- Add description_th column
ALTER TABLE ai_audit_document_types ADD COLUMN description_th TEXT;

-- Update seed records with Thai descriptions
UPDATE ai_audit_document_types SET description_th = 'รูปถ่ายขยะหรือวัสดุรีไซเคิลที่จุดรวบรวมหรือคัดแยก ใช้สำหรับยืนยันประเภทและสภาพของขยะ' WHERE id = 1;
UPDATE ai_audit_document_types SET description_th = 'แบบฟอร์มบันทึกน้ำหนักรายวันที่กรอกโดยเจ้าหน้าที่ ประกอบด้วยวันที่และน้ำหนักวัสดุที่บันทึกตลอดทั้งวัน' WHERE id = 2;
UPDATE ai_audit_document_types SET description_th = 'แบบฟอร์มสรุปน้ำหนักรายเดือน ประกอบด้วยน้ำหนักรวมของวัสดุแต่ละชนิดในแต่ละเดือน' WHERE id = 3;
UPDATE ai_audit_document_types SET description_th = 'ใบชั่งน้ำหนักที่ออกเมื่อมีการซื้อขายหรือโอนวัสดุ ประกอบด้วยรายละเอียดการชั่ง ผู้ซื้อ ผู้ขาย และน้ำหนักวัสดุ' WHERE id = 4;
UPDATE ai_audit_document_types SET description_th = 'ใบเสร็จรับเงินหรือใบแจ้งหนี้จากการขายวัสดุ ประกอบด้วยรายการวัสดุพร้อมจำนวน ราคา และยอดรวม' WHERE id = 5;
