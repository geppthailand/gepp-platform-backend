-- Migration: Insert mock data for currencies
-- Date: 2025-01-09
-- Description: Insert comprehensive currency data including THB with ID 12

-- Clear existing currencies first to avoid conflicts
DELETE FROM currencies;

-- Reset the sequence to start from 1
SELECT setval(pg_get_serial_sequence('currencies', 'id'), 1, false);

-- Insert comprehensive currency data with specific IDs
INSERT INTO currencies (id, name_en, name_th, code, symbol, created_date, updated_date, is_active) VALUES
    -- Major currencies
    (1, 'US Dollar', 'ดอลลาร์สหรัฐ', 'USD', '$', NOW(), NOW(), TRUE),
    (2, 'Euro', 'ยูโร', 'EUR', '€', NOW(), NOW(), TRUE),
    (3, 'British Pound', 'ปอนด์อังกฤษ', 'GBP', '£', NOW(), NOW(), TRUE),
    (4, 'Japanese Yen', 'เยนญี่ปุ่น', 'JPY', '¥', NOW(), NOW(), TRUE),
    (5, 'Chinese Yuan', 'หยวนจีน', 'CNY', '¥', NOW(), NOW(), TRUE),
    
    -- Southeast Asian currencies
    (10, 'Singapore Dollar', 'ดอลลาร์สิงคโปร์', 'SGD', 'S$', NOW(), NOW(), TRUE),
    (11, 'Malaysian Ringgit', 'รินกิตมาเลเซีย', 'MYR', 'RM', NOW(), NOW(), TRUE),
    (12, 'Thai Baht', 'บาทไทย', 'THB', '฿', NOW(), NOW(), TRUE),
    (13, 'Indonesian Rupiah', 'รูเปียห์อินโดนีเซีย', 'IDR', 'Rp', NOW(), NOW(), TRUE),
    (14, 'Philippine Peso', 'เปโซฟิลิปปินส์', 'PHP', '₱', NOW(), NOW(), TRUE),
    (15, 'Vietnamese Dong', 'ดองเวียดนาม', 'VND', '₫', NOW(), NOW(), TRUE),
    
    -- Other Asian currencies
    (20, 'South Korean Won', 'วอนเกาหลีใต้', 'KRW', '₩', NOW(), NOW(), TRUE),
    (21, 'Taiwan Dollar', 'ดอลลาร์ไต้หวัน', 'TWD', 'NT$', NOW(), NOW(), TRUE),
    (22, 'Hong Kong Dollar', 'ดอลลาร์ฮ่องกง', 'HKD', 'HK$', NOW(), NOW(), TRUE),
    (23, 'Indian Rupee', 'รูปีอินเดีย', 'INR', '₹', NOW(), NOW(), TRUE),
    
    -- Middle Eastern currencies
    (30, 'UAE Dirham', 'เดอร์แฮมสหรัฐอาหรับเอมิเรตส์', 'AED', 'د.إ', NOW(), NOW(), TRUE),
    (31, 'Saudi Riyal', 'ริยาลซาอุดีอาระเบีย', 'SAR', '﷼', NOW(), NOW(), TRUE),
    (32, 'Qatari Riyal', 'ริยาลกาตาร์', 'QAR', '﷼', NOW(), NOW(), TRUE),
    (33, 'Kuwaiti Dinar', 'ดีนาร์คูเวต', 'KWD', 'د.ك', NOW(), NOW(), TRUE),
    
    -- Other major currencies
    (40, 'Australian Dollar', 'ดอลลาร์ออสเตรเลีย', 'AUD', 'A$', NOW(), NOW(), TRUE),
    (41, 'Canadian Dollar', 'ดอลลาร์แคนาดา', 'CAD', 'C$', NOW(), NOW(), TRUE),
    (42, 'Swiss Franc', 'ฟรังค์สวิส', 'CHF', 'CHF', NOW(), NOW(), TRUE),
    (43, 'Swedish Krona', 'โครนาสวีเดน', 'SEK', 'kr', NOW(), NOW(), TRUE),
    (44, 'Norwegian Krone', 'โครเนนอร์เวย์', 'NOK', 'kr', NOW(), NOW(), TRUE),
    (45, 'Danish Krone', 'โครเนเดนมาร์ก', 'DKK', 'kr', NOW(), NOW(), TRUE),
    
    -- South American currencies
    (50, 'Brazilian Real', 'เรียลบราซิล', 'BRL', 'R$', NOW(), NOW(), TRUE),
    (51, 'Argentine Peso', 'เปโซอาร์เจนตินา', 'ARS', '$', NOW(), NOW(), TRUE),
    (52, 'Chilean Peso', 'เปโซชิลี', 'CLP', '$', NOW(), NOW(), TRUE),
    (53, 'Mexican Peso', 'เปโซเม็กซิโก', 'MXN', '$', NOW(), NOW(), TRUE);

-- Update the sequence to the next available number
SELECT setval(pg_get_serial_sequence('currencies', 'id'), 100, true);