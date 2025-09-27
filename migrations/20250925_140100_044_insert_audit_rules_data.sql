-- Migration: Insert audit rules data from Excel file
-- Version: v1.044
-- Date: 2025-09-25
-- Description: Insert 17 audit rules with their configurations and actions

-- Add missing enum values for rule_type_enum
-- Note: Each enum value addition must be in its own transaction
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'rule_type_enum') THEN
        -- Add validation enum value if it doesn't exist
        IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'validation' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'rule_type_enum')) THEN
            ALTER TYPE rule_type_enum ADD VALUE 'validation';
        END IF;
    END IF;
END
$$;

-- Commit the first enum value addition
COMMIT;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'rule_type_enum') THEN
        -- Add improvement enum value if it doesn't exist
        IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'improvement' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'rule_type_enum')) THEN
            ALTER TYPE rule_type_enum ADD VALUE 'improvement';
        END IF;
    END IF;
END
$$;

-- Commit the second enum value addition
COMMIT;

-- Add missing columns to audit_rules table if they don't exist
ALTER TABLE audit_rules ADD COLUMN IF NOT EXISTS is_global BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE audit_rules ADD COLUMN IF NOT EXISTS organization_id BIGINT REFERENCES organizations(id);

-- Create indexes for the new columns
CREATE INDEX IF NOT EXISTS idx_audit_rules_is_global ON audit_rules(is_global);
CREATE INDEX IF NOT EXISTS idx_audit_rules_organization_id ON audit_rules(organization_id);

-- Add column comments
COMMENT ON COLUMN audit_rules.is_global IS 'Whether this rule applies to all organizations (true) or is organization-specific (false)';
COMMENT ON COLUMN audit_rules.organization_id IS 'Organization ID for organization-specific rules, NULL for global rules';

-- Commit all schema changes before inserting data
COMMIT;

-- Insert audit rules data
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('DC-01', 'consistency', 'OCR Confidence Score', 'AI OCR ประมวลผลภาพเอกสารและให้คะแนนความมั่นใจในการอ่านแต่ละฟิลด์', 'ค่า Confidence Score ของฟิลด์สำคัญ (เช่น ราคารวม, วันที่) ต่ำกว่าเกณฑ์ที่กำหนด', 'Confidence Score < 95%', 'แสดงกรอบสีเหลืองรอบฟิลด์ที่ AI ไม่มั่นใจ พร้อมระบุ "AI confidence: [X]%"', '[{"type": "system_action", "action": "Flag for Auditor Review"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('DC-02', 'consistency', 'Price Mismatch', 'เปรียบเทียบค่าตัวเลขในฟิลด์ "ราคา" ที่ผู้ใช้กรอก กับค่าที่ OCR อ่านได้จากเอกสาร', 'User_Input_Price ≠ OCR_Extracted_Price', '-', 'Highlight ทั้ง 2 ฟิลด์ด้วยสีแดง แสดงไอคอน "ไม่ตรงกัน"', '[{"type": "system_action", "action": "Flag for Auditor Review"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('DC-03', 'consistency', 'Sub-material Mismatch', 'ตรวจสอบรายการสินค้า/วัสดุย่อย (Line Items) ที่ผู้ใช้กรอก เทียบกับตารางในเอกสารที่ OCR อ่านได้', '1. จำนวนรายการไม่ตรงกัน<br>2. ชื่อรายการไม่ตรงกัน (ใช้ Levenshtein distance)<br>3. จำนวน/ราคาต่อหน่วยไม่ตรงกัน', 'Levenshtein Distance > 2', 'แสดงตารางเปรียบเทียบ Side-by-Side ชี้ให้เห็นแถวที่ไม่ตรงกัน', '[{"type": "system_action", "action": "Flag for Auditor Review"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('DC-04', 'consistency', 'Invalid Date Logic', 'ตรวจสอบตรรกะของวันที่ 2 ข้อ:<br>1. Format ของวันที่<br>2. ลำดับเวลาของวันที่', '1. OCR_Date_Format ไม่ตรงกับ Format ที่ยอมรับ (เช่น DD/MM/YYYY)<br>2. Invoice_Date > Submission_Date', '-', 'แสดงข้อความแจ้งเตือนชัดเจน เช่น "วันที่ในเอกสารอยู่ในอนาคต" หรือ "รูปแบบวันที่ไม่ถูกต้อง"', '[{"type": "system_action", "action": "Flag for Auditor Review"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('DC-05', 'consistency', 'Impossible Value Check', 'ตรวจสอบค่าตัวเลขว่ามีความเป็นไปได้ทางตรรกะหรือไม่', 'Price ≤ 0 <br> Quantity ≤ 0', 'Value ≤ 0', 'Highlight ฟิลด์ที่มีปัญหาด้วยสีแดง พร้อมข้อความ "ค่าข้อมูลไม่ถูกต้อง"', '[{"type": "system_action", "action": "Flag for Auditor Review"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('RR-01', 'redundancy', 'Exact Duplicate (Same User)', 'ตรวจสอบ Image_Hash + UserID เทียบกับฐานข้อมูลเอกสารที่เคยส่งมาทั้งหมด', 'พบ Image_Hash และ UserID ที่ตรงกันในประวัติ', '100% Match', 'แสดงข้อความ "เอกสารซ้ำ: คุณเคยส่งเอกสารนี้แล้วเมื่อ [วัน/เวลา]"', '[{"type": "system_action", "action": "Auto-Reject"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('RR-02', 'redundancy', 'Potential Fraud (Cross-User Duplicate)', 'ตรวจสอบ Image_Hash เทียบกับฐานข้อมูลทั้งหมด โดยไม่สนใจ UserID', 'พบ Image_Hash ที่ตรงกัน แต่ UserID ไม่ตรงกัน', '100% Match', 'แสดงข้อความ "ความเสี่ยงสูง: เอกสารนี้เคยถูกส่งโดยผู้ใช้อื่น (ID: [XXXX])"', '[{"type": "system_action", "action": "Flag for High-Priority Auditor Review"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('RR-03', 'redundancy', 'Near-Duplicate Image', 'ใช้ Perceptual Hash (pHash) เพื่อเปรียบเทียบความคล้ายคลึงทางภาพ แม้มีการแก้ไขเล็กน้อย (เช่น crop, เปลี่ยนสี)', 'ระยะห่าง (Hamming Distance) ระหว่าง pHash ของเอกสารใหม่กับเอกสารเก่า ต่ำกว่าเกณฑ์', 'Hamming Distance < 5 (ปรับค่าได้)', 'แสดงภาพเอกสารที่คล้ายกันขึ้นมาเปรียบเทียบ พร้อมระบุ "% ความคล้าย"', '[{"type": "system_action", "action": "Flag for Auditor Review"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('RR-04', 'redundancy', 'High Text Similarity', 'ใช้ NLP (BERT Embedding + Cosine Similarity) เพื่อเปรียบเทียบเนื้อหาข้อความทั้งหมดที่ OCR อ่านได้', 'Similarity_Score > เกณฑ์ที่กำหนด', '> 90%', 'แสดงข้อความ "เนื้อหามีความคล้ายคลึง [XX]% กับเอกสาร [Doc ID]" พร้อม Highlight ส่วนที่คล้ายกัน', '[{"type": "system_action", "action": "Flag for Auditor Review"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('WF-01', 'validation', 'Audit Score Calculation', 'ระบบรวมผลลัพธ์จากกฎทั้งหมด (DC-xx, RR-xx) มาคำนวณเป็นคะแนนความน่าเชื่อถือ', 'ทุกครั้งที่มีการส่งเอกสาร', '-', 'แสดงคะแนนใน Dashboard (เช่น 98/100) พร้อมสรุปจำนวน Flags', '[{"type": "system_action", "action": "ใช้คะแนนในการตัดสินใจขั้นตอนถัดไป"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('WF-02', 'validation', 'Automated Routing', 'จัดการเอกสารตาม Audit Score และ Flags ที่เกิดขึ้น', '1. ไม่มี Flags เลย และ Audit Score = 100<br>2. มี Flags 1 ประเภทขึ้นไป หรือ Audit Score < 100', '-', '-', '[{"type": "system_action", "action": "Auto-Approve"}, {"type": "system_action", "action": "Route to Auditor Queue"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('WF-03', 'validation', 'Human-in-the-loop Decision', 'Auditor ตรวจสอบเอกสารที่ถูก Flag', 'Auditor กดปุ่ม Action บน UI', '-', 'UI แสดงปุ่ม 3 ปุ่มชัดเจน: อนุมัติ (Approve), ปฏิเสธ (Reject), ขอแก้ไข (Request Edit)', '[{"type": "human_action", "action": "Auditor ตัดสินใจ"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('WF-04', 'validation', 'Mandatory Rejection Reason', 'หาก Auditor กด "ปฏิเสธ" ระบบบังคับให้เลือกเหตุผลจาก Dropdown หรือกรอกข้อมูล', 'Action == "Reject"', '-', 'แสดง Modal/Popup ให้เลือกเหตุผล (เช่น "ข้อมูลไม่ตรง", "เอกสารปลอม")', '[{"type": "system_action", "action": "บันทึกเหตุผลลง Audit Log เพื่อใช้ในส่วนที่ 4"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('WF-05', 'validation', 'Immutable Audit Log', 'ทุกการกระทำที่เกิดขึ้นกับเอกสาร (AI check, Auditor view, Auditor decision) จะถูกบันทึก', 'ทุก State Change ของเอกสาร', '-', 'แสดงประวัติการตรวจสอบ (Timeline View) ในหน้า Transaction Detail', '[{"type": "system_action", "action": "Write Log to Database"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('CI-01', 'improvement', 'Feedback Loop Activation', 'รวบรวมข้อมูลการตัดสินใจของ Auditor (โดยเฉพาะเคสที่ Override ผล AI) เพื่อสร้าง Dataset สำหรับการเทรนใหม่', 'Auditor ตัดสินใจแตกต่างจากที่ AI แนะนำ (เช่น AI ไม่ Flag แต่คน Reject)', '> 50 overrides ใน 1 สัปดาห์', 'แสดงกราฟ "AI vs Human Disagreement Rate"', '[{"type": "system_action", "action": "ส่ง Notification ให้ Data Scientist/ML Engineer"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('CI-02', 'improvement', 'Automated ML Retraining Pipeline', 'ระบบนำ Dataset ใหม่ (จาก CI-01) มา Fine-tune โมเดล AI (OCR/NLP) โดยอัตโนมัติ', '1. ถูก Trigger โดย CI-01<br>2. ตามรอบเวลาที่กำหนด (เช่น ทุก 1 เดือน)', '-', 'แสดง "Last Model Update: [Date]" และ "Accuracy Improvement: [X]%"', '[{"type": "system_action", "action": "Deploy โมเดลใหม่หลังจากผ่านการทดสอบ"}]', true, NULL);
INSERT INTO audit_rules (rule_id, rule_type, rule_name, process, condition, thresholds, metrics, actions, is_global, organization_id)
VALUES ('CI-03', 'improvement', 'Dynamic Threshold Adjustment', 'Product Owner/Manager วิเคราะห์ข้อมูลจาก Dashboard เพื่อปรับปรุงเกณฑ์ (Thresholds) ของกฎต่างๆ', 'Business Policy เปลี่ยนแปลง หรือพบแนวโน้มการทุจริตรูปแบบใหม่', '-', 'Dashboard แสดง "Top 5 Rejection Reasons" และ "Rules with High Override Rate"', '[{"type": "human_action", "action": "Product Owner ปรับค่า Thresholds ในหน้า Admin Panel"}]', true, NULL);

-- Verify insertion
SELECT rule_type, COUNT(*) as rule_count
FROM audit_rules
WHERE is_active = true
GROUP BY rule_type
ORDER BY rule_type;