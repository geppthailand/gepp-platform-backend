# คู่มือการใช้งาน BMA Integration API

## เริ่มต้นใช้งาน

### ขั้นตอนที่ 1: เข้าถึง Swagger Documentation

เปิดเว็บเบราว์เซอร์และเข้าไปที่:
```
https://api.geppdata.com/v1/docs/bma/0a70bf9ef2fcb7c2dc6c2b046ebb052c
```

### ขั้นตอนที่ 2: ใช้งาน JWT Token

**JWT Token สำหรับทดสอบ:**
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoyNiwib3JnYW5pemF0aW9uX2lkIjo4LCJlbWFpbCI6ImJtYUBnZXBwLm1lIiwidHlwZSI6ImludGVncmF0aW9uIiwiZXhwIjoxNzYyMjM4NTA2LCJpYXQiOjE3NjE2MzM3MDZ9.q1v6QIH_14c_sNAomOYvoMYNmmlPhgPBPyTsA4KB1Oo
```

**วิธีใช้งาน:**
1. คัดลอก JWT Token ข้างต้น
2. ใน Swagger UI คลิกปุ่ม **"Authorize"** ที่มุมบนขวา
3. วาง Token ในช่อง Value (ไม่ต้องใส่คำว่า "Bearer" ข้างหน้า)
4. คลิก **"Authorize"** แล้วปิดหน้าต่าง

**หมายเหตุ:** ใช้ Token นี้ได้เลยโดยไม่ต้องเรียก `/api/auth/integration` ก่อน

---

## ⚠️ ข้อมูลสำคัญ

**origin_id สำหรับ API นี้:**
- ใช้ค่า **2170** เท่านั้น
- แทนพื้นที่: **แขวงช่องนนทรี**
- ใช้เป็น Mock Data สำหรับ API version นี้
- ในอนาคตอาจมีการเพิ่ม origin_id อื่นๆ สำหรับแขวงต่างๆ

**ห้ามใช้ origin_id อื่นนอกเหนือจาก 2170** มิฉะนั้นจะได้รับ Error

---

## คำศัพท์และตัวแปรสำคัญ

### 1. ตัวระบุข้อมูล (Identifiers)

#### `transaction_version` (ext_id_1)
- **คืออะไร**: รุ่นของการบันทึกข้อมูล เช่น "v2025-Q1", "v2025-Q2"
- **รูปแบบ**: ใช้ตามความต้องการของคุณ แนะนำให้ใช้รูปแบบ vYYYY-XX ซึ่งอาจหมายถึงไตรมาส เดือน หรือจำนวนครั้งที่สำหรับปีนั้นๆได้
- **ตัวอย่าง**: `"v2025-Q1"`, `"v2025-Q2"`, `"v2025-10"`
- **วัตถุประสงค์**: ใช้จัดกลุ่มข้อมูลตามช่วงเวลาหรือรอบการเก็บข้อมูล

#### `house_id` (ext_id_2)
- **คืออะไร**: รหัสบ้านเลขที่
- **รูปแบบแนะนำ**: เลข 11 หลัก เช่น `"00000000001"`, `"00000000002"`
- **ตัวอย่าง**: `"00000000001"` (บ้านเลขที่ 1), `"00000000123"` (บ้านเลขที่ 123)
- **เหตุผล**: รูปแบบนี้ทำให้เรียงลำดับได้ง่ายและสม่ำเสมอ

#### `origin_id`
- **คืออะไร**: รหัสจุดรับของเสีย
- **ค่าที่ใช้ได้**: **2170 เท่านั้น**
- **origin_name**: "แขวงช่องนนทรี"
- **หมายเหตุ**:
  - ระบบรองรับเฉพาะ origin_id 2170 สำหรับ BMA
  - รหัส 2170 แทนแขวงช่องนนทรี ซึ่งใช้เป็น Mock Data สำหรับ API version นี้
  - ในอนาคตอาจมีการเพิ่ม origin_id อื่นๆ สำหรับแขวงอื่นๆ

### 2. ประเภทขยะ (Material Types)

| ชื่อภาษาอังกฤษ | ชื่อภาษาไทย | material_id | ใช้ใน API |
|----------------|-------------|-------------|-----------|
| **general** | ขยะทั่วไป | 94 | `"general"` |
| **organic** | ขยะอินทรีย์/อาหาร | 77 | `"organic"` |
| **recyclable** | ขยะรีไซเคิล | 298 | `"recyclable"` |
| **hazardous** | ขยะอันตราย | 113 | `"hazardous"` |

**คำอธิบาย:**
- **general**: ขยะทั่วไป ไม่สามารถนำกลับมาใช้ใหม่ได้
- **organic**: ขยะเปียก เศษอาหาร เศษพืช
- **recyclable**: ขยะแห้งที่สามารถนำกลับมาใช้ใหม่ได้ เช่น กระดาษ พลาสติก
- **hazardous**: ขยะอันตราย เช่น แบตเตอรี่ สารเคมี

### 3. Pagination (การแบ่งหน้า)

#### `limit`
- **คืออะไร**: จำนวนรายการต่อหน้า
- **ค่าเริ่มต้น**: 100
- **ค่าสูงสุด**: 1000
- **ตัวอย่าง**: `?limit=50` (แสดง 50 รายการต่อหน้า)

#### `page`
- **คืออะไร**: หมายเลขหน้า
- **ค่าเริ่มต้น**: 1
- **เริ่มนับจาก**: 1 (หน้าแรกคือหน้าที่ 1)
- **ตัวอย่าง**: `?page=2` (แสดงหน้าที่ 2)

**ข้อมูล Pagination ที่ได้รับกลับมา:**
```json
{
  "pagination": {
    "page": 1,              // หน้าปัจจุบัน
    "limit": 100,           // จำนวนรายการต่อหน้า
    "total": 250,           // จำนวนรายการทั้งหมด
    "total_pages": 3,       // จำนวนหน้าทั้งหมด
    "has_next": true,       // มีหน้าถัดไปหรือไม่
    "has_prev": false       // มีหน้าก่อนหน้าหรือไม่
  }
}
```

### 4. Quota และ Usage (โควต้าการใช้งาน)

#### `create_transaction_limit`
- **คืออะไร**: จำนวนครั้งสูงสุดที่สามารถสร้าง Transaction ได้
- **หน่วย**: ครั้ง/เดือน
- **ดูได้จาก**: `/api/integration/bma/usage`

#### `create_transaction_usage`
- **คืออะไร**: จำนวนครั้งที่ใช้ไปแล้วในการสร้าง Transaction
- **การคำนวณ**:
  - ✅ **นับ**: เมื่อสร้าง Transaction **ใหม่** (create)
  - ❌ **ไม่นับ**: เมื่ออัพเดท Transaction เดิม (update)
  - นับทีละ 1 ต่อ 1 house_id ที่สร้างใหม่
- **ตัวอย่าง**: ส่ง 10 บ้านใหม่ = เพิ่ม 10, ส่ง 10 บ้านเดิม (อัพเดท) = ไม่เพิ่ม
- **ดูได้จาก**: `/api/integration/bma/usage`

#### `ai_audit_limit`
- **คืออะไร**: จำนวนครั้งสูงสุดที่สามารถใช้ AI Audit ได้
- **หน่วย**: ครั้ง/เดือน
- **ดูได้จาก**: `/api/integration/bma/usage`

#### `ai_audit_usage`
- **คืออะไร**: จำนวนครั้งที่ใช้ AI Audit ไปแล้ว
- **การคำนวณ**:
  - ✅ **นับ**: ทุกครั้งที่ส่ง Transaction เข้าระบบ AI Audit
  - นับทั้งการสร้างใหม่ (create) และอัพเดท (update)
  - นับทีละ 1 ต่อ 1 Transaction ที่ส่งเข้า Audit
- **ตัวอย่าง**: ส่งเข้า Audit 5 Transaction = เพิ่ม 5
- **ดูได้จาก**: `/api/integration/bma/usage`

### 5. Audit Status และ Violations

#### `ai_audit` (สถานะ AI Audit)
- **คืออะไร**: ผลการตรวจสอบโดย AI
- **ค่าที่เป็นไปได้**:
  - `"null"` - ยังไม่ได้ตรวจสอบ
  - `"queued"` - อยู่ในคิวรอตรวจสอบ
  - `"approved"` - ผ่านการตรวจสอบ
  - `"rejected"` - ไม่ผ่านการตรวจสอบ
  - `"no_action"` - ไม่ต้องดำเนินการ

**⚠️ สำคัญ:** ใช้ `ai_audit` เป็นสถานะหลักแทน `status`

#### `status` (สถานะทั่วไป)
- **คืออะไร**: สถานะทั่วไปของ Transaction
- **ค่าที่เป็นไปได้**: pending, approved, rejected, completed
- **หมายเหตุ**: ไม่แนะนำให้ใช้ ให้ใช้ `ai_audit` แทน

#### `overall_violations`
- **คืออะไร**: รายการข้อผิดพลาดระดับบ้าน (ไม่เจาะจงประเภทขยะ)
- **รูปแบบ**: Array ของข้อความ
- **ตัวอย่าง**:
```json
"overall_violations": [
  "ภาพไม่ชัดเจน กรุณาถ่ายใหม่",
  "ไม่พบข้อมูลที่อยู่"
]
```

#### `violations` (ระดับประเภทขยะ)
- **คืออะไร**: รายการข้อผิดพลาดเฉพาะประเภทขยะ
- **ตำแหน่ง**: อยู่ภายใต้แต่ละประเภทขยะใน materials
- **ตัวอย่าง**:
```json
"materials": {
  "general": {
    "image_url": "...",
    "violations": [
      "พบขยะรีไซเคิลปนในถังขยะทั่วไป",
      "ขยะไม่ได้คัดแยก"
    ]
  }
}
```

#### `image_url`
- **คืออะไร**: URL ของรูปภาพขยะ
- **รูปแบบ**: URL แบบ S3 หรือ HTTPS
- **ตัวอย่าง**: `"https://s3.example.com/bma/house001-general.jpg"`
- **ตำแหน่ง**: อยู่ภายใต้แต่ละประเภทขยะ
- **⚠️ ข้อกำหนดสำคัญ**:
  - **ต้องเป็น Public URL** ที่สามารถเข้าถึงได้โดยไม่ต้อง Authentication
  - ระบบจะดึงรูปภาพจาก URL นี้เพื่อส่งไป AI Audit
  - หาก URL ไม่สามารถเข้าถึงได้ การ Audit จะล้มเหลว
  - แนะนำใช้ S3 Presigned URL หรือ Public Bucket

---

## การใช้งาน API แต่ละตัว

### 1. ตรวจสอบสถานะการ Audit

**Endpoint:** `GET /api/integration/bma/audit_status`

**วัตถุประสงค์:** ดูสถิติการตรวจสอบของ Transaction ย้อนหลัง 1 ปี

**วิธีใช้:**
1. ไปที่ Swagger UI
2. เลือก **GET /api/integration/bma/audit_status**
3. คลิก **"Try it out"**
4. คลิก **"Execute"**

**Response ที่ได้รับ:**
```json
{
  "success": true,
  "data": {
    "start_date": "2024-10-27",
    "num_transactions": 150,
    "ai_audit": {
      "not_audit": 45,      // ยังไม่ได้ตรวจ
      "queued": 30,         // รอตรวจ
      "approved": 50,       // ผ่าน
      "rejected": 25        // ไม่ผ่าน
    },
    "actual_status": {
      "pending": 60,        // รอดำเนินการ
      "approved": 70,       // อนุมัติ
      "rejected": 20        // ปฏิเสธ
    }
  }
}
```

**คำอธิบายข้อมูล:**
- `start_date`: วันที่เริ่มนับ (1 ปีย้อนหลัง)
- `num_transactions`: จำนวน Transaction ทั้งหมด
- `ai_audit`: สถิติการตรวจสอบโดย AI
- `actual_status`: สถิติสถานะจริงของ Transaction

---

### 2. ตรวจสอบโควต้าการใช้งาน

**Endpoint:** `GET /api/integration/bma/usage`

**วัตถุประสงค์:** ดูโควต้าและการใช้งานปัจจุบัน

**วิธีใช้:**
1. ไปที่ Swagger UI
2. เลือก **GET /api/integration/bma/usage**
3. คลิก **"Try it out"**
4. คลิก **"Execute"**

**Response ที่ได้รับ:**
```json
{
  "success": true,
  "data": {
    "create_transaction_limit": 1000,    // โควต้าสูงสุด
    "create_transaction_usage": 450,     // ใช้ไปแล้ว
    "ai_audit_limit": 100,               // โควต้า AI
    "ai_audit_usage": 35                 // ใช้ AI ไปแล้ว
  }
}
```

**การตีความข้อมูล:**
- สามารถสร้าง Transaction ได้อีก: `1000 - 450 = 550 ครั้ง`
- สามารถใช้ AI Audit ได้อีก: `100 - 35 = 65 ครั้ง`

**เมื่อไหร่ควรตรวจสอบ:**
- ก่อนส่งข้อมูลจำนวนมาก
- เมื่อได้รับ Error เกี่ยวกับโควต้า
- เพื่อวางแผนการใช้งานประจำเดือน

---

### 3. บันทึกข้อมูลขยะ (Batch Upload)

**Endpoint:** `POST /api/integration/bma/transaction`

**วัตถุประสงค์:** บันทึกข้อมูลขยะทีละหลายบ้านในคลิกเดียว

**💡 แนะนำ:**
- **สามารถส่งหลายๆ house_id พร้อมกันได้** ในคำขอเดียว (Batch Processing)
- **แนะนำไม่เกิน 1,000 house_id ต่อครั้ง** เพื่อประสิทธิภาพที่ดีที่สุด
- หากมีข้อมูลมากกว่า 1,000 บ้าน ควรแบ่งส่งหลายๆ ครั้ง

**รูปแบบข้อมูล:**
```json
{
  "batch": {
    "v2025-Q1": {                    // transaction_version
      "2170": {                      // origin_id (ต้องเป็น 2170 = แขวงช่องนนทรี)
        "00000000001": {             // house_id (บ้านเลขที่)
          "timestamp": "2025-10-23T08:30:00+07:00",
          "material": {
            "general": {             // ขยะทั่วไป
              "image_url": "https://s3.example.com/bma/house001-general.jpg"
            },
            "recyclable": {          // ขยะรีไซเคิล
              "image_url": "https://s3.example.com/bma/house001-recyclable.jpg"
            }
          }
        },
        "00000000002": {             // บ้านที่ 2
          "timestamp": "2025-10-23T09:15:00+07:00",
          "material": {
            "organic": {             // ขยะอินทรีย์
              "image_url": "https://s3.example.com/bma/house002-organic.jpg"
            }
          }
        }
      }
    }
  }
}
```

**วิธีใช้งานใน Swagger:**
1. เลือก **POST /api/integration/bma/transaction**
2. คลิก **"Try it out"**
3. แก้ไข Request body ตามรูปแบบข้างต้น
4. เปลี่ยน:
   - `transaction_version` ให้ตรงกับรุ่นของคุณ
   - `house_id` เป็นรหัสบ้านจริง (11 หลัก)
   - `timestamp` เป็นเวลาที่เก็บขยะ
   - `image_url` เป็น URL รูปภาพจริง
5. คลิก **"Execute"**

**Response ที่ได้รับ:**
```json
{
  "success": true,
  "message": "Processed 2 transactions",
  "results": {
    "processed": 2,               // ประมวลผลทั้งหมด
    "created": 2,                 // สร้างใหม่
    "updated": 0,                 // อัพเดท
    "errors": []                  // ข้อผิดพลาด (ถ้ามี)
  },
  "subscription_usage": {
    "create_transaction_limit": 1000,
    "create_transaction_usage": 452,     // เพิ่มขึ้น 2
    "ai_audit_limit": 100,
    "ai_audit_usage": 35
  }
}
```

**กรณีมี Error:**
```json
{
  "success": true,
  "results": {
    "processed": 2,
    "created": 1,
    "updated": 1,
    "errors": [
      {
        "transaction_version": "v2025-Q1",
        "house_id": "00000000003",
        "error": "Invalid timestamp format"
      }
    ]
  }
}
```

**ข้อควรระวัง:**
- ใช้ `origin_id` เป็น **2170** เท่านั้น
- `timestamp` ต้องเป็นรูปแบบ ISO 8601 พร้อม timezone
- `image_url` **ต้องเป็น Public URL** ที่ระบบสามารถเข้าถึงได้โดยไม่ต้อง authentication
- ถ้าบันทึกบ้านเดิมซ้ำ (transaction_version + house_id เหมือนกัน) จะเป็นการ**อัพเดท**

---

### 4. ดึงรายการข้อมูลขยะ (List)

**Endpoint:** `GET /api/integration/bma/transaction`

**วัตถุประสงค์:** ดูรายการข้อมูลขยะทั้งหมดพร้อมแบ่งหน้า

**Parameters:**
- `limit` (optional): จำนวนต่อหน้า (ค่าเริ่มต้น: 100, สูงสุด: 1000)
- `page` (optional): หมายเลขหน้า (ค่าเริ่มต้น: 1)
- `transaction_version` (optional): กรองตามรุ่น
- `origin_id` (optional): กรองตามจุดรับ

**ตัวอย่างการใช้งาน:**

**ดูหน้าแรก (100 รายการ):**
```
GET /api/integration/bma/transaction
```

**ดูหน้าที่ 2, แสดง 50 รายการ:**
```
GET /api/integration/bma/transaction?page=2&limit=50
```

**กรองเฉพาะรุ่น v2025-Q1:**
```
GET /api/integration/bma/transaction?transaction_version=v2025-Q1
```

**กรองรุ่น v2025-Q1 จาก origin 2170 หน้าที่ 3:**
```
GET /api/integration/bma/transaction?transaction_version=v2025-Q1&origin_id=2170&page=3&limit=100
```

**วิธีใช้ใน Swagger:**
1. เลือก **GET /api/integration/bma/transaction**
2. คลิก **"Try it out"**
3. กรอก Parameters ที่ต้องการ
4. คลิก **"Execute"**

**Response ที่ได้รับ:**
```json
{
  "success": true,
  "data": {
    "transactions": {
      "v2025-Q1": {                      // transaction_version
        "2170": {                        // origin_id
          "00000000001": {               // house_id
            "audit": {
              "status": "pending",
              "ai_audit": "approved",    // ⭐ ใช้ตัวนี้เป็นสถานะหลัก
              "overall_violations": [
                "ภาพไม่ชัดเจน"           // ข้อผิดพลาดระดับบ้าน
              ],
              "materials": {
                "general": {
                  "image_url": "https://...",
                  "violations": [        // ข้อผิดพลาดเฉพาะประเภท
                    "พบขยะรีไซเคิลปน"
                  ]
                },
                "organic": {
                  "image_url": "https://...",
                  "violations": []
                }
              }
            }
          }
        }
      }
    },
    "origins": {
      "2170": "แขวงช่องนนทรี"   // ชื่อจุดรับ
    },
    "pagination": {
      "page": 1,
      "limit": 100,
      "total": 250,
      "total_pages": 3,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

**โครงสร้างข้อมูล:**
```
transactions
└── [transaction_version]
    └── [origin_id]
        └── [house_id]
            └── audit
                ├── status: สถานะทั่วไป
                ├── ai_audit: ⭐ สถานะ AI (ใช้ตัวนี้)
                ├── overall_violations: ข้อผิดพลาดระดับบ้าน
                └── materials
                    ├── general
                    │   ├── image_url
                    │   └── violations
                    ├── organic
                    ├── recyclable
                    └── hazardous
```

**การนำไปใช้:**
- ตรวจสอบสถานะด้วย `ai_audit` ไม่ใช่ `status`
- `overall_violations` = ปัญหาทั่วไปของบ้าน
- `violations` ใน materials = ปัญหาเฉพาะประเภทขยะ
- ถ้า `violations` เป็น `[]` = ไม่มีปัญหา

---

### 5. ดูข้อมูลบ้านเฉพาะเจาะจง

**Endpoint:** `GET /api/integration/bma/transaction/{transaction_version}/{house_id}`

**วัตถุประสงค์:** ดูข้อมูลบ้านเดียวแบบละเอียด

**Parameters:**
- `transaction_version`: รุ่นของข้อมูล (เช่น "v2025-Q1")
- `house_id`: รหัสบ้าน (เช่น "00000000001")

**ตัวอย่างการใช้งาน:**

**ดูบ้านเลขที่ 1 รุ่น v2025-Q1:**
```
GET /api/integration/bma/transaction/v2025-Q1/00000000001
```

**วิธีใช้ใน Swagger:**
1. เลือก **GET /api/integration/bma/transaction/{transaction_version}/{house_id}**
2. คลิก **"Try it out"**
3. กรอก `transaction_version` เช่น `v2025-Q1`
4. กรอก `house_id` เช่น `00000000001`
5. คลิก **"Execute"**

**Response ที่ได้รับ:**
```json
{
  "success": true,
  "data": {
    "transaction_version": "v2025-Q1",
    "house_id": "00000000001",
    "origin_id": "2170",
    "origin_name": "แขวงช่องนนทรี",
    "audit": {
      "status": "pending",
      "ai_audit": "rejected",              // ⭐ สถานะ AI
      "overall_violations": [
        "ภาพไม่ชัดเจน กรุณาถ่ายใหม่",
      ],
      "materials": {
        "general": {
          "image_url": "https://s3.example.com/bma/house001-general.jpg",
          "violations": [
            "พบขยะรีไซเคิลปนอยู่ในถังขยะทั่วไป",
          ]
        },
        "recyclable": {
          "image_url": "https://s3.example.com/bma/house001-recyclable.jpg",
          "violations": []                 // ไม่มีปัญหา
        },
        "organic": {
          "image_url": null,               // ไม่มีรูป
          "violations": []
        },
        "hazardous": {
          "image_url": null,
          "violations": []
        }
      }
    }
  }
}
```

**การตีความผลลัพธ์:**

**บ้านนี้มีปัญหา:**
- `ai_audit = "rejected"` → ไม่ผ่าน AI Audit
- `overall_violations` มี 2 รายการ → ปัญหาระดับบ้าน
- ขยะทั่วไป (general) มี `violations` 2 รายการ → ปัญหาเฉพาะประเภท
- ขยะรีไซเคิล (recyclable) ไม่มีปัญหา

**แนวทางแก้ไข:**
1. ถ่ายภาพใหม่ให้ชัดเจน
2. ถ่ายป้ายบ้านเลขที่ให้เห็น
3. คัดแยกขยะรีไซเคิลออกจากถังขยะทั่วไป
4. ส่งข้อมูลใหม่ (POST) ด้วย transaction_version และ house_id เดิม (จะเป็นการอัพเดท)

---

## กรณีตัวอย่างการใช้งานจริง

### สถานการณ์ที่ 1: ส่งข้อมูลบ้านใหม่ 10 บ้าน

**ขั้นตอน:**

1. **ตรวจสอบโควต้า:**
   ```
   GET /api/integration/bma/usage
   ```
   ตรวจสอบว่า `create_transaction_usage` + 10 ไม่เกิน `create_transaction_limit`

2. **เตรียมข้อมูล:**
   ```json
   {
     "batch": {
       "v2025-Q1": {
         "2170": {
           "00000000001": { "timestamp": "...", "material": {...} },
           "00000000002": { "timestamp": "...", "material": {...} },
           ...
           "00000000010": { "timestamp": "...", "material": {...} }
         }
       }
     }
   }
   ```

3. **ส่งข้อมูล:**
   ```
   POST /api/integration/bma/transaction
   ```

4. **ตรวจสอบผล:**
   - ดู `results.created` ควรเป็น 10
   - ดู `results.errors` ถ้ามีบ้านไหนผิดพลาด

---

### สถานการณ์ที่ 2: ตรวจสอบบ้านที่ไม่ผ่าน AI Audit

**ขั้นตอน:**

1. **ดูสถิติ:**
   ```
   GET /api/integration/bma/audit_status
   ```
   ดู `ai_audit.rejected` มีกี่บ้าน

2. **ดูรายการทั้งหมด:**
   ```
   GET /api/integration/bma/transaction?limit=1000
   ```

3. **กรองในโปรแกรม:** หาบ้านที่ `ai_audit = "rejected"`

4. **ดูรายละเอียด:**
   ```
   GET /api/integration/bma/transaction/v2025-Q1/00000000123
   ```
   ดู `overall_violations` และ `violations` ในแต่ละประเภทขยะ

5. **แก้ไขและส่งใหม่:**
   ```json
   {
     "batch": {
       "v2025-Q1": {
         "2170": {
           "00000000123": {
             "timestamp": "2025-10-24T10:00:00+07:00",
             "material": {
               "general": {
                 "image_url": "https://... (รูปใหม่)"
               }
             }
           }
         }
       }
     }
   }
   ```

---

### สถานการณ์ที่ 3: ดึงข้อมูลเดือนตุลาคม 2025

**ขั้นตอน:**

1. **กรองตามรุ่น:**
   ```
   GET /api/integration/bma/transaction?transaction_version=v2025-10&limit=1000
   ```

2. **ถ้ามีเกิน 1000 รายการ:**
   ```
   GET /api/integration/bma/transaction?transaction_version=v2025-10&page=1&limit=1000
   GET /api/integration/bma/transaction?transaction_version=v2025-10&page=2&limit=1000
   ...
   ```
   ดูจนกว่า `pagination.has_next = false`

3. **ประมวลผลข้อมูล:** วนลูปผ่านทุก transaction และตรวจสอบ `ai_audit` status

---

### สถานการณ์ที่ 4: ส่งข้อมูลจำนวนมาก (มากกว่า 1,000 บ้าน)

**สถานการณ์:** มีข้อมูล 2,500 บ้านที่ต้องส่งเข้าระบบ

**วิธีการ:** แบ่งส่งเป็นหลายๆ ครั้ง ครั้งละไม่เกิน 1,000 บ้าน

**ขั้นตอน:**

1. **ตรวจสอบโควต้า:**
   ```
   GET /api/integration/bma/usage
   ```
   ตรวจสอบว่ามี quota เพียงพอ (2,500 บ้าน)

2. **แบ่งข้อมูลออกเป็น 3 ชุด:**
   - ชุดที่ 1: บ้าน 1-1,000 (1,000 บ้าน)
   - ชุดที่ 2: บ้าน 1,001-2,000 (1,000 บ้าน)
   - ชุดที่ 3: บ้าน 2,001-2,500 (500 บ้าน)

3. **ส่งชุดที่ 1 (1,000 บ้านแรก):**
   ```json
   POST /api/integration/bma/transaction
   {
     "batch": {
       "v2025-Q1": {
         "2170": {
           "00000000001": { "timestamp": "...", "material": {...} },
           "00000000002": { "timestamp": "...", "material": {...} },
           ...
           "00000001000": { "timestamp": "...", "material": {...} }
         }
       }
     }
   }
   ```
   **Response:**
   ```json
   {
     "success": true,
     "message": "Processed 1000 transactions",
     "results": {
       "processed": 1000,
       "created": 1000,
       "updated": 0,
       "errors": []
     }
   }
   ```

4. **ส่งชุดที่ 2 (1,000 บ้านถัดไป):**
   ```json
   POST /api/integration/bma/transaction
   {
     "batch": {
       "v2025-Q1": {
         "2170": {
           "00000001001": { "timestamp": "...", "material": {...} },
           "00000001002": { "timestamp": "...", "material": {...} },
           ...
           "00000002000": { "timestamp": "...", "material": {...} }
         }
       }
     }
   }
   ```
   **Response:**
   ```json
   {
     "success": true,
     "message": "Processed 1000 transactions",
     "results": {
       "processed": 1000,
       "created": 1000,
       "updated": 0,
       "errors": []
     }
   }
   ```

5. **ส่งชุดที่ 3 (500 บ้านสุดท้าย):**
   ```json
   POST /api/integration/bma/transaction
   {
     "batch": {
       "v2025-Q1": {
         "2170": {
           "00000002001": { "timestamp": "...", "material": {...} },
           "00000002002": { "timestamp": "...", "material": {...} },
           ...
           "00000002500": { "timestamp": "...", "material": {...} }
         }
       }
     }
   }
   ```
   **Response:**
   ```json
   {
     "success": true,
     "message": "Processed 500 transactions",
     "results": {
       "processed": 500,
       "created": 500,
       "updated": 0,
       "errors": []
     }
   }
   ```

6. **ตรวจสอบผลรวม:**
   - ส่งทั้งหมด: 1,000 + 1,000 + 500 = 2,500 บ้าน
   - `create_transaction_usage` เพิ่มขึ้น 2,500
   - ตรวจสอบ `errors` ในแต่ละ response

**ประโยชน์ของการแบ่งส่ง:**
- ✅ ป้องกัน Request Timeout (คำขอไม่หมดเวลา)
- ✅ ติดตาม Error ได้ง่ายขึ้น (รู้ชุดไหนผิด)
- ✅ สามารถ Retry เฉพาะชุดที่มีปัญหา
- ✅ ประมวลผลเร็วขึ้น

**ตัวอย่างโค้ด JavaScript สำหรับแบ่งส่ง:**
```javascript
async function sendBatchInChunks(allHouses, chunkSize = 1000) {
  const results = {
    totalSent: 0,
    totalCreated: 0,
    totalUpdated: 0,
    allErrors: []
  };

  // แบ่งข้อมูลเป็น chunks
  for (let i = 0; i < allHouses.length; i += chunkSize) {
    const chunk = allHouses.slice(i, i + chunkSize);
    console.log(`Sending chunk ${Math.floor(i/chunkSize) + 1}...`);

    // เตรียม batch data
    const batchData = {
      batch: {
        "v2025-Q1": {
          "2170": {}
        }
      }
    };

    // เติมข้อมูลบ้าน
    chunk.forEach(house => {
      batchData.batch["v2025-Q1"]["2170"][house.id] = {
        timestamp: house.timestamp,
        material: house.material
      };
    });

    // ส่ง request
    try {
      const response = await fetch('/api/integration/bma/transaction', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer YOUR_JWT_TOKEN',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(batchData)
      });

      const data = await response.json();

      // รวมผลลัพธ์
      results.totalSent += data.results.processed;
      results.totalCreated += data.results.created;
      results.totalUpdated += data.results.updated;
      results.allErrors.push(...data.results.errors);

      console.log(`✅ Chunk ${Math.floor(i/chunkSize) + 1} done: ${data.results.created} created`);

    } catch (error) {
      console.error(`❌ Chunk ${Math.floor(i/chunkSize) + 1} failed:`, error);
      results.allErrors.push({
        chunk: Math.floor(i/chunkSize) + 1,
        error: error.message
      });
    }

    // พักเล็กน้อยระหว่างแต่ละ chunk (optional)
    await new Promise(resolve => setTimeout(resolve, 1000));
  }

  return results;
}

// ใช้งาน
const allHouses = [
  { id: "00000000001", timestamp: "...", material: {...} },
  { id: "00000000002", timestamp: "...", material: {...} },
  // ... 2,500 บ้าน
];

const results = await sendBatchInChunks(allHouses, 1000);
console.log('Summary:', results);
```

**สรุป:**
- 📊 ข้อมูลมาก = แบ่งส่ง
- 🔢 แนะนำไม่เกิน 1,000 บ้านต่อครั้ง
- ⏱️ ป้องกันปัญหา timeout
- 🔍 ติดตาม error ได้ง่ายขึ้น

---

## ข้อควรระวังและคำแนะนำ

### ✅ สิ่งที่ควรทำ

1. **ใช้ `ai_audit` แทน `status`**
   ```javascript
   // ถูกต้อง ✅
   if (transaction.audit.ai_audit === "approved") {
     // ผ่าน
   }

   // ไม่แนะนำ ❌
   if (transaction.audit.status === "approved") {
     // อาจไม่ตรงกับผล AI
   }
   ```

2. **ใช้ house_id แบบ 11 หลัก**
   ```
   ✅ "00000000001", "00000000123"
   ❌ "HOUSE-001", "1", "H001"
   ```

3. **ใช้ origin_id เป็น 2170 เท่านั้น**
   ```json
   ✅ "2170"  // แขวงช่องนนทรี (Mock Data)
   ❌ "2171", "1234", อื่นๆ
   ```

4. **ตรวจสอบโควต้าก่อนส่งข้อมูลจำนวนมาก**

5. **ระบุ timestamp ให้ถูกต้อง**
   ```
   ✅ "2025-10-23T08:30:00+07:00"  (ISO 8601 + timezone)
   ❌ "2025-10-23 08:30:00"
   ❌ "23/10/2025"
   ```

6. **ใช้ image_url ที่สามารถเข้าถึงได้**
   ```
   ✅ "https://s3.amazonaws.com/bucket/image.jpg"  (Public URL)
   ✅ "https://storage.googleapis.com/bucket/image.jpg"  (Public GCS)
   ✅ "https://s3.example.com/image.jpg?AWSAccessKeyId=..."  (Presigned URL)
   ❌ "file:///local/path/image.jpg"  (Local file)
   ❌ "https://private.example.com/image.jpg"  (ต้อง authentication)
   ```
   **หมายเหตุ**: ระบบต้องสามารถดาวน์โหลดรูปภาพได้เพื่อส่งไป AI Audit

### ⚠️ สิ่งที่ควรหลีกเลี่ยง

1. **ส่ง origin_id ไม่ใช่ 2170**
   - จะได้ Error: "Only origin_id 2170 is allowed for BMA integration"

2. **ส่งข้อมูลซ้ำโดยไม่ตั้งใจ**
   - ถ้า transaction_version + house_id เหมือนกัน = อัพเดท (ไม่ใช่สร้างใหม่)
   - ตรวจสอบให้แน่ใจว่าต้องการอัพเดทจริง

3. **ไม่ได้อ่าน violations**
   - AI Audit อาจ reject แต่ `overall_violations` และ `violations` จะบอกสาเหตุ
   - อ่านทุกครั้งเพื่อปรับปรุงข้อมูล

4. **ใช้ limit สูงเกินไปโดยไม่จำเป็น**
   - limit=1000 จะช้ากว่า limit=100
   - ใช้แค่พอดีกับที่ต้องการ

5. **ใช้ image_url ที่เข้าถึงไม่ได้**
   - URL ต้องเป็น Public หรือ Presigned URL ที่ระบบดาวน์โหลดได้
   - ถ้า URL ไม่สามารถเข้าถึง จะทำให้ AI Audit ล้มเหลว
   - ตรวจสอบว่า URL ยังใช้งานได้ (ไม่หมดอายุ) ก่อนส่ง

---

## ตัวอย่างการตรวจสอบและแก้ไข

### ขั้นตอนการตรวจสอบข้อมูลที่ส่งไปแล้ว

```javascript
// 1. ดึงข้อมูลทั้งหมด
const response = await fetch('/api/integration/bma/transaction?limit=100');
const data = await response.json();

// 2. วนลูปตรวจสอบแต่ละบ้าน
for (const version in data.data.transactions) {
  for (const origin in data.data.transactions[version]) {
    for (const houseId in data.data.transactions[version][origin]) {
      const house = data.data.transactions[version][origin][houseId];
      const audit = house.audit;

      // 3. ตรวจสอบสถานะ AI Audit
      if (audit.ai_audit === "rejected") {
        console.log(`บ้าน ${houseId} ไม่ผ่าน AI Audit`);

        // 4. ดูปัญหาระดับบ้าน
        if (audit.overall_violations.length > 0) {
          console.log("ปัญหาทั่วไป:", audit.overall_violations);
        }

        // 5. ดูปัญหาแต่ละประเภทขยะ
        for (const materialType in audit.materials) {
          const material = audit.materials[materialType];
          if (material.violations.length > 0) {
            console.log(`ปัญหา${materialType}:`, material.violations);
          }
        }
      }
    }
  }
}
```

---

## สรุป

### API ทั้ง 5 ตัว

| Endpoint | Method | วัตถุประสงค์ |
|----------|--------|-------------|
| `/audit_status` | GET | ดูสถิติการ Audit |
| `/usage` | GET | ดูโควต้า |
| `/transaction` | POST | ส่งข้อมูลขยะ (batch) |
| `/transaction` | GET | ดูรายการทั้งหมด |
| `/transaction/{version}/{id}` | GET | ดูบ้านเจาะจง |

### ค่าสำคัญที่ต้องจำ

- **origin_id**: 2170 เท่านั้น
- **house_id**: แนะนำ 11 หลัก (00000000001)
- **สถานะ**: ใช้ `ai_audit` ไม่ใช่ `status`
- **ขยะ**: general, organic, recyclable, hazardous

### Link สำคัญ

- **Swagger UI**: https://api.geppdata.com/v1/docs/bma/0a70bf9ef2fcb7c2dc6c2b046ebb052c
- **JWT Token**: [ใช้ Token ที่ให้ไว้ด้านบน]

---

**หากมีปัญหาหรือข้อสงสัย:**
- กรุณาติดต่อทีมงาน GEPP Sa-Ard 
