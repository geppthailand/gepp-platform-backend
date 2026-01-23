-- Migration: Insert mock data for location_countries
-- Date: 2025-01-09
-- Description: Insert comprehensive country data including Thailand with ID 212

-- Clear existing countries first to avoid conflicts
DELETE FROM location_countries;

-- Reset the sequence to start from 1
SELECT setval(pg_get_serial_sequence('location_countries', 'id'), 1, false);

-- Insert comprehensive country data with specific IDs
INSERT INTO location_countries (id, name_en, name_th, code, phone_code, currency_code, created_date, updated_date, is_active) VALUES
    -- Southeast Asia
    (1, 'Thailand', 'ประเทศไทย', 'TH', '+66', 'THB', NOW(), NOW(), TRUE),
    (2, 'Malaysia', 'มาเลเซีย', 'MY', '+60', 'MYR', NOW(), NOW(), TRUE),
    (3, 'Singapore', 'สิงคโปร์', 'SG', '+65', 'SGD', NOW(), NOW(), TRUE),
    (4, 'Indonesia', 'อินโดนีเซีย', 'ID', '+62', 'IDR', NOW(), NOW(), TRUE),
    (5, 'Philippines', 'ฟิลิปปินส์', 'PH', '+63', 'PHP', NOW(), NOW(), TRUE),
    (6, 'Vietnam', 'เวียดนาม', 'VN', '+84', 'VND', NOW(), NOW(), TRUE),
    (7, 'Cambodia', 'กัมพูชา', 'KH', '+855', 'KHR', NOW(), NOW(), TRUE),
    (8, 'Laos', 'ลาว', 'LA', '+856', 'LAK', NOW(), NOW(), TRUE),
    (9, 'Myanmar', 'พม่า', 'MM', '+95', 'MMK', NOW(), NOW(), TRUE),
    (10, 'Brunei', 'บรูไน', 'BN', '+673', 'BND', NOW(), NOW(), TRUE),
    
    -- East Asia
    (20, 'China', 'จีน', 'CN', '+86', 'CNY', NOW(), NOW(), TRUE),
    (21, 'Japan', 'ญี่ปุ่น', 'JP', '+81', 'JPY', NOW(), NOW(), TRUE),
    (22, 'South Korea', 'เกาหลีใต้', 'KR', '+82', 'KRW', NOW(), NOW(), TRUE),
    (23, 'North Korea', 'เกาหลีเหนือ', 'KP', '+850', 'KPW', NOW(), NOW(), TRUE),
    (24, 'Taiwan', 'ไต้หวัน', 'TW', '+886', 'TWD', NOW(), NOW(), TRUE),
    (25, 'Hong Kong', 'ฮ่องกง', 'HK', '+852', 'HKD', NOW(), NOW(), TRUE),
    (26, 'Macau', 'มาเก๊า', 'MO', '+853', 'MOP', NOW(), NOW(), TRUE),
    
    -- South Asia
    (30, 'India', 'อินเดีย', 'IN', '+91', 'INR', NOW(), NOW(), TRUE),
    (31, 'Pakistan', 'ปากีสถาน', 'PK', '+92', 'PKR', NOW(), NOW(), TRUE),
    (32, 'Bangladesh', 'บังคลาเทศ', 'BD', '+880', 'BDT', NOW(), NOW(), TRUE),
    (33, 'Sri Lanka', 'ศรีลังกา', 'LK', '+94', 'LKR', NOW(), NOW(), TRUE),
    (34, 'Nepal', 'เนปาล', 'NP', '+977', 'NPR', NOW(), NOW(), TRUE),
    (35, 'Bhutan', 'ภูฏาน', 'BT', '+975', 'BTN', NOW(), NOW(), TRUE),
    (36, 'Maldives', 'มัลดีฟส์', 'MV', '+960', 'MVR', NOW(), NOW(), TRUE),
    
    -- Americas
    (100, 'United States', 'สหรัฐอเมริกา', 'US', '+1', 'USD', NOW(), NOW(), TRUE),
    (101, 'Canada', 'แคนาดา', 'CA', '+1', 'CAD', NOW(), NOW(), TRUE),
    (102, 'Mexico', 'เม็กซิโก', 'MX', '+52', 'MXN', NOW(), NOW(), TRUE),
    (103, 'Brazil', 'บราซิล', 'BR', '+55', 'BRL', NOW(), NOW(), TRUE),
    (104, 'Argentina', 'อาร์เจนตินา', 'AR', '+54', 'ARS', NOW(), NOW(), TRUE),
    (105, 'Chile', 'ชิลี', 'CL', '+56', 'CLP', NOW(), NOW(), TRUE),
    
    -- Europe
    (150, 'United Kingdom', 'สหราชอาณาจักร', 'GB', '+44', 'GBP', NOW(), NOW(), TRUE),
    (151, 'Germany', 'เยอรมนี', 'DE', '+49', 'EUR', NOW(), NOW(), TRUE),
    (152, 'France', 'ฝรั่งเศส', 'FR', '+33', 'EUR', NOW(), NOW(), TRUE),
    (153, 'Italy', 'อิตาลี', 'IT', '+39', 'EUR', NOW(), NOW(), TRUE),
    (154, 'Spain', 'สเปน', 'ES', '+34', 'EUR', NOW(), NOW(), TRUE),
    (155, 'Netherlands', 'เนเธอร์แลนด์', 'NL', '+31', 'EUR', NOW(), NOW(), TRUE),
    (156, 'Switzerland', 'สวิตเซอร์แลนด์', 'CH', '+41', 'CHF', NOW(), NOW(), TRUE),
    (157, 'Sweden', 'สวีเดน', 'SE', '+46', 'SEK', NOW(), NOW(), TRUE),
    (158, 'Norway', 'นอร์เวย์', 'NO', '+47', 'NOK', NOW(), NOW(), TRUE),
    (159, 'Denmark', 'เดนมาร์ก', 'DK', '+45', 'DKK', NOW(), NOW(), TRUE),
    
    -- Middle East
    (200, 'United Arab Emirates', 'สหรัฐอาหรับเอมิเรตส์', 'AE', '+971', 'AED', NOW(), NOW(), TRUE),
    (201, 'Saudi Arabia', 'ซาอุดีอาระเบีย', 'SA', '+966', 'SAR', NOW(), NOW(), TRUE),
    (202, 'Israel', 'อิสราเอล', 'IL', '+972', 'ILS', NOW(), NOW(), TRUE),
    (203, 'Turkey', 'ตุรกี', 'TR', '+90', 'TRY', NOW(), NOW(), TRUE),
    (204, 'Qatar', 'กาตาร์', 'QA', '+974', 'QAR', NOW(), NOW(), TRUE),
    (205, 'Kuwait', 'คูเวต', 'KW', '+965', 'KWD', NOW(), NOW(), TRUE),
    
    -- Oceania
    (210, 'Australia', 'ออสเตรเลีย', 'AU', '+61', 'AUD', NOW(), NOW(), TRUE),
    (211, 'New Zealand', 'นิวซีแลนด์', 'NZ', '+64', 'NZD', NOW(), NOW(), TRUE),
    
    -- Special entry for Thailand with ID 212 (the one referenced in user_locations default)
    (212, 'Thailand (Default)', 'ประเทศไทย (ค่าเริ่มต้น)', 'TH_DEFAULT', '+66', 'THB', NOW(), NOW(), TRUE);

-- Update the sequence to the next available number
SELECT setval(pg_get_serial_sequence('location_countries', 'id'), 250, true);