# Notification Messages Design Document

**Version**: 1.0.0
**Created Date**: January 27, 2026
**Status**: Design Phase

---

## Overview

This document defines all notification message templates for the GEPP Platform. Messages are provided in both Thai and English, with role-specific variations where applicable.

---

## Table of Contents

1. [Message Template Format](#message-template-format)
2. [Transaction Event Messages](#transaction-event-messages)
3. [Organization Event Messages](#organization-event-messages)
4. [Location Event Messages](#location-event-messages)
5. [User & Member Event Messages](#user--member-event-messages)
6. [System Event Messages](#system-event-messages)
7. [Report Notification Messages](#report-notification-messages)
8. [Email Templates](#email-templates)
9. [Bell Notification Templates](#bell-notification-templates)

---

## Message Template Format

### Variable Placeholders

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{transaction_id}` | Transaction ID | `TXN-2026-001234` |
| `{transaction_date}` | Transaction date | `27/01/2026` |
| `{user_name}` | User display name | `สมชาย ใจดี` |
| `{location_name}` | Location name | `สาขากรุงเทพฯ` |
| `{organization_name}` | Organization name | `บริษัท ABC จำกัด` |
| `{material_type}` | Material/waste type | `วัสดุรีไซเคิล` |
| `{weight_kg}` | Weight in kg | `150.5` |
| `{amount_thb}` | Amount in THB | `2,500.00` |
| `{status}` | Transaction status | `อนุมัติ` |
| `{count}` | Count number | `15` |
| `{date_range}` | Date range | `1-31 ม.ค. 2569` |
| `{role_name}` | Role name | `ผู้ตรวจสอบ` |
| `{reason}` | Reason/note | `ข้อมูลไม่ครบถ้วน` |
| `{violation_details}` | Violation details | `พบวัสดุอันตรายปนเปื้อน` |
| `{link}` | Action link | `https://app.gepp.com/transactions/123` |

---

## Transaction Event Messages

### TXN_CREATED - Transaction Created

#### For Admin

**Thai (Bell)**
```
สร้างรายการใหม่: {transaction_id}
{user_name} สร้างรายการวัสดุ {material_type} น้ำหนัก {weight_kg} กก.
ที่สาขา {location_name}
```

**Thai (Email Subject)**
```
[GEPP] รายการใหม่ #{transaction_id} - {organization_name}
```

**Thai (Email Body)**
```
เรียน ผู้ดูแลระบบ,

มีการสร้างรายการใหม่ในระบบ GEPP:

รหัสรายการ: {transaction_id}
วันที่: {transaction_date}
ผู้สร้าง: {user_name}
สาขา: {location_name}
ประเภทวัสดุ: {material_type}
น้ำหนัก: {weight_kg} กก.
มูลค่า: {amount_thb} บาท

คลิกเพื่อดูรายละเอียด: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
New Transaction: {transaction_id}
{user_name} created {material_type} transaction, {weight_kg} kg
at {location_name}
```

**English (Email Subject)**
```
[GEPP] New Transaction #{transaction_id} - {organization_name}
```

#### For Data Inputter (Own Transaction)

**Thai (Bell)**
```
สร้างรายการสำเร็จ: {transaction_id}
รายการวัสดุ {material_type} น้ำหนัก {weight_kg} กก. รอการตรวจสอบ
```

**English (Bell)**
```
Transaction Created: {transaction_id}
{material_type}, {weight_kg} kg - Pending review
```

#### For Auditor

**Thai (Bell)**
```
รายการใหม่รอตรวจสอบ: {transaction_id}
{user_name} สร้างรายการ {material_type} ที่สาขา {location_name}
```

**English (Bell)**
```
New Transaction Pending Review: {transaction_id}
{user_name} created {material_type} at {location_name}
```

---

### TXN_UPDATED - Transaction Updated

#### For Admin

**Thai (Bell)**
```
อัปเดตรายการ: {transaction_id}
{user_name} แก้ไขรายการวัสดุ {material_type}
```

**Thai (Email Subject)**
```
[GEPP] อัปเดตรายการ #{transaction_id} - {organization_name}
```

**Thai (Email Body)**
```
เรียน ผู้ดูแลระบบ,

มีการอัปเดตรายการในระบบ GEPP:

รหัสรายการ: {transaction_id}
วันที่อัปเดต: {transaction_date}
ผู้แก้ไข: {user_name}
สาขา: {location_name}

การเปลี่ยนแปลง:
{changes_summary}

คลิกเพื่อดูรายละเอียด: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
Transaction Updated: {transaction_id}
{user_name} modified {material_type} transaction
```

#### For Data Inputter (Own Transaction)

**Thai (Bell)**
```
อัปเดตรายการสำเร็จ: {transaction_id}
รายการของคุณถูกอัปเดตเรียบร้อยแล้ว
```

**English (Bell)**
```
Transaction Updated: {transaction_id}
Your transaction has been updated successfully
```

---

### TXN_SUBMITTED - Transaction Submitted for Review

#### For Auditor

**Thai (Bell)**
```
รายการรอตรวจสอบ: {transaction_id}
{user_name} ส่งรายการ {material_type} รอการตรวจสอบ
ที่สาขา {location_name}
```

**Thai (Email Subject)**
```
[GEPP] รายการรอตรวจสอบ #{transaction_id} - {organization_name}
```

**Thai (Email Body)**
```
เรียน ผู้ตรวจสอบ,

มีรายการใหม่รอการตรวจสอบในระบบ GEPP:

รหัสรายการ: {transaction_id}
วันที่: {transaction_date}
ผู้ส่ง: {user_name}
สาขา: {location_name}
ประเภทวัสดุ: {material_type}
น้ำหนัก: {weight_kg} กก.
มูลค่า: {amount_thb} บาท

กรุณาตรวจสอบและอนุมัติรายการ
คลิกเพื่อตรวจสอบ: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
Transaction Pending Review: {transaction_id}
{user_name} submitted {material_type} for review
at {location_name}
```

---

### TXN_APPROVED - Transaction Approved

#### For Admin

**Thai (Bell)**
```
อนุมัติรายการ: {transaction_id}
{auditor_name} อนุมัติรายการจากสาขา {location_name}
```

**English (Bell)**
```
Transaction Approved: {transaction_id}
{auditor_name} approved transaction from {location_name}
```

#### For Data Inputter (Own Transaction)

**Thai (Bell)**
```
รายการได้รับอนุมัติ: {transaction_id}
รายการ {material_type} น้ำหนัก {weight_kg} กก. ได้รับการอนุมัติแล้ว
```

**Thai (Email Subject)**
```
[GEPP] รายการได้รับอนุมัติ #{transaction_id}
```

**Thai (Email Body)**
```
เรียน {user_name},

รายการของคุณได้รับการอนุมัติแล้ว:

รหัสรายการ: {transaction_id}
วันที่: {transaction_date}
ประเภทวัสดุ: {material_type}
น้ำหนัก: {weight_kg} กก.
มูลค่า: {amount_thb} บาท
สถานะ: อนุมัติ

ผู้อนุมัติ: {auditor_name}
วันที่อนุมัติ: {approved_date}

คลิกเพื่อดูรายละเอียด: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
Transaction Approved: {transaction_id}
Your {material_type} transaction ({weight_kg} kg) has been approved
```

**English (Email Subject)**
```
[GEPP] Transaction Approved #{transaction_id}
```

#### For Auditor

**Thai (Bell)**
```
อนุมัติรายการสำเร็จ: {transaction_id}
คุณอนุมัติรายการจาก {user_name} ที่สาขา {location_name}
```

**English (Bell)**
```
Approval Confirmed: {transaction_id}
You approved transaction from {user_name} at {location_name}
```

#### For Viewer

**Thai (Bell)**
```
รายการใหม่ที่อนุมัติ: {transaction_id}
วัสดุ {material_type} น้ำหนัก {weight_kg} กก. จากสาขา {location_name}
```

**English (Bell)**
```
New Approved Transaction: {transaction_id}
{material_type}, {weight_kg} kg from {location_name}
```

---

### TXN_REJECTED - Transaction Rejected

#### For Admin

**Thai (Bell)**
```
ปฏิเสธรายการ: {transaction_id}
{auditor_name} ปฏิเสธรายการจากสาขา {location_name}
เหตุผล: {reason}
```

**English (Bell)**
```
Transaction Rejected: {transaction_id}
{auditor_name} rejected transaction from {location_name}
Reason: {reason}
```

#### For Data Inputter (Own Transaction)

**Thai (Bell)**
```
รายการถูกปฏิเสธ: {transaction_id}
รายการ {material_type} ไม่ผ่านการตรวจสอบ
เหตุผล: {reason}
```

**Thai (Email Subject)**
```
[GEPP] รายการถูกปฏิเสธ #{transaction_id} - กรุณาแก้ไข
```

**Thai (Email Body)**
```
เรียน {user_name},

รายการของคุณถูกปฏิเสธ กรุณาตรวจสอบและแก้ไข:

รหัสรายการ: {transaction_id}
วันที่: {transaction_date}
ประเภทวัสดุ: {material_type}
น้ำหนัก: {weight_kg} กก.
สถานะ: ไม่อนุมัติ

ผู้ตรวจสอบ: {auditor_name}
เหตุผล: {reason}

รายละเอียดเพิ่มเติม:
{rejection_details}

กรุณาแก้ไขและส่งรายการใหม่
คลิกเพื่อแก้ไข: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
Transaction Rejected: {transaction_id}
Your {material_type} transaction was not approved
Reason: {reason}
```

**English (Email Subject)**
```
[GEPP] Transaction Rejected #{transaction_id} - Action Required
```

---

### TXN_AI_AUDIT_COMPLETED - AI Audit Completed

#### For Admin

**Thai (Bell)**
```
AI ตรวจสอบเสร็จสิ้น: {transaction_id}
ผลการตรวจสอบ: {status}
ความมั่นใจ: {confidence_score}%
```

**Thai (Email Subject)**
```
[GEPP] ผลการตรวจสอบด้วย AI #{transaction_id} - {status}
```

**Thai (Email Body)**
```
เรียน ผู้ดูแลระบบ,

การตรวจสอบด้วย AI สำหรับรายการ #{transaction_id} เสร็จสิ้น:

รหัสรายการ: {transaction_id}
วันที่: {transaction_date}
สาขา: {location_name}
ประเภทวัสดุ: {material_type}

ผลการตรวจสอบ AI:
- สถานะ: {status}
- คะแนนความมั่นใจ: {confidence_score}%
- จำนวนข้อผิดพลาด: {violation_count}

{violation_details}

คลิกเพื่อดูรายละเอียด: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
AI Audit Complete: {transaction_id}
Result: {status}
Confidence: {confidence_score}%
```

#### For Data Inputter (Own Transaction)

**Thai (Bell)**
```
AI ตรวจสอบรายการของคุณเสร็จสิ้น: {transaction_id}
ผล: {status} - {violation_count} ข้อผิดพลาด
```

**English (Bell)**
```
AI Audit Complete for Your Transaction: {transaction_id}
Result: {status} - {violation_count} violation(s)
```

#### For Auditor

**Thai (Bell)**
```
AI ตรวจสอบเสร็จสิ้น: {transaction_id}
ผล: {status} - รอการยืนยัน
จากสาขา {location_name}
```

**Thai (Email Subject)**
```
[GEPP] AI ตรวจสอบเสร็จ #{transaction_id} - รอการยืนยัน
```

**Thai (Email Body)**
```
เรียน ผู้ตรวจสอบ,

การตรวจสอบด้วย AI เสร็จสิ้น รอการยืนยันจากคุณ:

รหัสรายการ: {transaction_id}
วันที่: {transaction_date}
ผู้สร้าง: {user_name}
สาขา: {location_name}

ผลการตรวจสอบ AI:
- สถานะแนะนำ: {status}
- คะแนนความมั่นใจ: {confidence_score}%
- จำนวนข้อผิดพลาด: {violation_count}

รายละเอียดข้อผิดพลาด:
{violation_details}

กรุณาตรวจสอบและยืนยันผล
คลิกเพื่อยืนยัน: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
AI Audit Complete: {transaction_id}
Result: {status} - Awaiting confirmation
from {location_name}
```

---

### TXN_AUDIT_VIOLATION - Audit Violation Found

#### For All Roles (Admin, Data Inputter, Auditor)

**Thai (Bell)**
```
พบข้อผิดพลาด: {transaction_id}
{violation_count} ข้อผิดพลาดจากการตรวจสอบ
{violation_summary}
```

**Thai (Email Subject)**
```
[GEPP] พบข้อผิดพลาด #{transaction_id} - {violation_count} รายการ
```

**Thai (Email Body)**
```
เรียน {user_name},

พบข้อผิดพลาดจากการตรวจสอบรายการ #{transaction_id}:

รหัสรายการ: {transaction_id}
วันที่: {transaction_date}
สาขา: {location_name}
ประเภทวัสดุ: {material_type}

ข้อผิดพลาดที่พบ ({violation_count} รายการ):
{violation_list}

รายละเอียด:
{violation_details}

การดำเนินการที่แนะนำ:
{recommended_actions}

คลิกเพื่อดูและแก้ไข: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
Violations Found: {transaction_id}
{violation_count} violation(s) detected
{violation_summary}
```

---

### TXN_PENDING_REVIEW - Transaction Pending Review

#### For Auditor

**Thai (Bell)**
```
รายการรอตรวจสอบ: {count} รายการ
{oldest_days} วันที่รอนานที่สุด
กรุณาตรวจสอบโดยเร็ว
```

**Thai (Email Subject)**
```
[GEPP] รายการรอตรวจสอบ {count} รายการ - {organization_name}
```

**English (Bell)**
```
Pending Review: {count} transaction(s)
Oldest pending: {oldest_days} days
Please review soon
```

---

## Organization Event Messages

### ORG_CHART_UPDATED - Organization Chart Updated

#### For Admin

**Thai (Bell)**
```
อัปเดตผังองค์กร
{user_name} เปลี่ยนแปลงโครงสร้างองค์กร
การเปลี่ยนแปลง: {changes_summary}
```

**Thai (Email Subject)**
```
[GEPP] อัปเดตผังองค์กร - {organization_name}
```

**Thai (Email Body)**
```
เรียน ผู้ดูแลระบบ,

มีการเปลี่ยนแปลงผังองค์กรใน GEPP:

ผู้แก้ไข: {user_name}
วันที่: {update_date}

การเปลี่ยนแปลง:
{changes_details}

สาขาที่ได้รับผลกระทบ:
{affected_locations}

คลิกเพื่อดูผังองค์กร: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
Organization Chart Updated
{user_name} modified organization structure
Changes: {changes_summary}
```

#### For Data Inputter, Auditor, Viewer

**Thai (Bell)**
```
อัปเดตผังองค์กร
โครงสร้างองค์กรมีการเปลี่ยนแปลง
คลิกเพื่อดูรายละเอียด
```

**English (Bell)**
```
Organization Chart Updated
Organization structure has been modified
Click to view details
```

---

### ORG_SETTINGS_CHANGED - Organization Settings Changed

#### For Admin

**Thai (Bell)**
```
เปลี่ยนการตั้งค่าองค์กร
{user_name} อัปเดตการตั้งค่า: {settings_changed}
```

**Thai (Email Subject)**
```
[GEPP] เปลี่ยนการตั้งค่าองค์กร - {organization_name}
```

**Thai (Email Body)**
```
เรียน ผู้ดูแลระบบ,

มีการเปลี่ยนการตั้งค่าองค์กรใน GEPP:

ผู้แก้ไข: {user_name}
วันที่: {update_date}

การตั้งค่าที่เปลี่ยนแปลง:
{settings_details}

คลิกเพื่อดูการตั้งค่า: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
Organization Settings Changed
{user_name} updated settings: {settings_changed}
```

---

## Location Event Messages

### LOC_CREATED - Location Created

#### For Admin

**Thai (Bell)**
```
สร้างสาขาใหม่: {location_name}
{user_name} เพิ่มสาขาใหม่ในระบบ
```

**Thai (Email Subject)**
```
[GEPP] สาขาใหม่: {location_name} - {organization_name}
```

**Thai (Email Body)**
```
เรียน ผู้ดูแลระบบ,

มีการสร้างสาขาใหม่ในระบบ GEPP:

ชื่อสาขา: {location_name}
ผู้สร้าง: {user_name}
วันที่สร้าง: {created_date}
ที่อยู่: {location_address}

คลิกเพื่อจัดการสาขา: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
New Location Created: {location_name}
{user_name} added a new location
```

#### For Data Inputter, Auditor

**Thai (Bell)**
```
สาขาใหม่: {location_name}
เพิ่มสาขาใหม่ในองค์กร
```

**English (Bell)**
```
New Location: {location_name}
A new location has been added
```

---

### LOC_UPDATED - Location Updated

#### For Admin

**Thai (Bell)**
```
อัปเดตสาขา: {location_name}
{user_name} แก้ไขข้อมูลสาขา
```

**English (Bell)**
```
Location Updated: {location_name}
{user_name} modified location details
```

#### For Assigned Users

**Thai (Bell)**
```
สาขาของคุณถูกอัปเดต: {location_name}
การเปลี่ยนแปลง: {changes_summary}
```

**English (Bell)**
```
Your Location Updated: {location_name}
Changes: {changes_summary}
```

---

### LOC_TAG_CREATED - Location Tag Created

#### For Admin

**Thai (Bell)**
```
สร้างแท็กใหม่: {tag_name}
แท็กใหม่สำหรับสาขา {location_name}
```

**English (Bell)**
```
New Tag Created: {tag_name}
New tag for location {location_name}
```

#### For Assigned Users

**Thai (Bell)**
```
แท็กใหม่ในสาขาของคุณ: {tag_name}
สาขา: {location_name}
```

**English (Bell)**
```
New Tag in Your Location: {tag_name}
Location: {location_name}
```

---

## User & Member Event Messages

### USER_ADDED - User Added

#### For Admin

**Thai (Bell)**
```
ผู้ใช้ใหม่: {new_user_name}
บทบาท: {role_name}
สาขา: {location_name}
```

**Thai (Email Subject)**
```
[GEPP] ผู้ใช้ใหม่: {new_user_name} - {organization_name}
```

**Thai (Email Body)**
```
เรียน ผู้ดูแลระบบ,

มีผู้ใช้ใหม่เข้าร่วมองค์กร:

ชื่อ: {new_user_name}
อีเมล: {new_user_email}
บทบาท: {role_name}
สาขา: {location_name}
เพิ่มโดย: {added_by_name}
วันที่: {added_date}

คลิกเพื่อจัดการผู้ใช้: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
New User: {new_user_name}
Role: {role_name}
Location: {location_name}
```

---

### USER_ROLE_CHANGED - User Role Changed

#### For Admin

**Thai (Bell)**
```
เปลี่ยนบทบาท: {user_name}
จาก {old_role} เป็น {new_role}
```

**Thai (Email Subject)**
```
[GEPP] เปลี่ยนบทบาทผู้ใช้: {user_name}
```

**English (Bell)**
```
Role Changed: {user_name}
From {old_role} to {new_role}
```

#### For Affected User

**Thai (Bell)**
```
บทบาทของคุณเปลี่ยนแปลง
จาก {old_role} เป็น {new_role}
```

**Thai (Email Subject)**
```
[GEPP] บทบาทของคุณเปลี่ยนแปลง - {organization_name}
```

**Thai (Email Body)**
```
เรียน {user_name},

บทบาทของคุณในระบบ GEPP ได้เปลี่ยนแปลง:

บทบาทเดิม: {old_role}
บทบาทใหม่: {new_role}
เปลี่ยนโดย: {changed_by_name}
วันที่: {changed_date}

สิทธิ์การใช้งานใหม่ของคุณ:
{new_permissions}

หากมีคำถาม กรุณาติดต่อผู้ดูแลระบบ

คลิกเพื่อเข้าสู่ระบบ: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
Your Role Has Changed
From {old_role} to {new_role}
```

---

### USER_LOCATION_ASSIGNED - User Location Assigned

#### For Admin

**Thai (Bell)**
```
มอบหมายสาขา: {user_name}
ได้รับมอบหมายให้ดูแล {location_name}
```

**English (Bell)**
```
Location Assigned: {user_name}
Assigned to manage {location_name}
```

#### For Affected User

**Thai (Bell)**
```
คุณได้รับมอบหมายสาขาใหม่
สาขา: {location_name}
บทบาท: {role_name}
```

**Thai (Email Subject)**
```
[GEPP] มอบหมายสาขาใหม่: {location_name}
```

**Thai (Email Body)**
```
เรียน {user_name},

คุณได้รับมอบหมายให้ดูแลสาขาใหม่ในระบบ GEPP:

สาขา: {location_name}
บทบาท: {role_name}
มอบหมายโดย: {assigned_by_name}
วันที่: {assigned_date}

คุณสามารถเริ่มทำงานได้ทันที
คลิกเพื่อเข้าสู่สาขา: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
You've Been Assigned a New Location
Location: {location_name}
Role: {role_name}
```

---

## System Event Messages

### SYS_MAINTENANCE - System Maintenance

#### For All Users

**Thai (Bell)**
```
แจ้งปิดปรับปรุงระบบ
วันที่: {maintenance_date}
เวลา: {maintenance_time}
ระยะเวลา: {duration}
```

**Thai (Email Subject)**
```
[GEPP] แจ้งปิดปรับปรุงระบบ - {maintenance_date}
```

**Thai (Email Body)**
```
เรียน ผู้ใช้งานระบบ GEPP,

ขอแจ้งกำหนดการปิดปรับปรุงระบบ:

วันที่: {maintenance_date}
เวลา: {maintenance_time}
ระยะเวลาโดยประมาณ: {duration}

รายละเอียด:
{maintenance_details}

ในช่วงเวลาดังกล่าว ระบบจะไม่สามารถใช้งานได้ชั่วคราว
กรุณาวางแผนการทำงานล่วงหน้า

หากมีคำถาม กรุณาติดต่อฝ่ายสนับสนุน

ขอบคุณ,
ทีม GEPP Platform
```

**English (Bell)**
```
System Maintenance Notice
Date: {maintenance_date}
Time: {maintenance_time}
Duration: {duration}
```

---

### SYS_UPDATE - System Update

#### For Admin

**Thai (Bell)**
```
อัปเดตระบบใหม่
มีฟีเจอร์ใหม่: {feature_summary}
คลิกเพื่อดูรายละเอียด
```

**Thai (Email Subject)**
```
[GEPP] อัปเดตระบบใหม่ - ฟีเจอร์ใหม่พร้อมใช้งาน
```

**Thai (Email Body)**
```
เรียน ผู้ดูแลระบบ,

ระบบ GEPP มีการอัปเดตใหม่:

เวอร์ชัน: {version}
วันที่อัปเดต: {update_date}

ฟีเจอร์ใหม่:
{new_features}

การปรับปรุง:
{improvements}

คลิกเพื่อดูรายละเอียด: {link}

ขอบคุณ,
ทีม GEPP Platform
```

**English (Bell)**
```
System Update Available
New features: {feature_summary}
Click to view details
```

#### For Other Users

**Thai (Bell)**
```
ระบบอัปเดตใหม่
มีฟีเจอร์ใหม่พร้อมใช้งาน
```

**English (Bell)**
```
System Updated
New features available
```

---

## Report Notification Messages

### RPT_TXN_DAILY - Daily Transaction Summary

#### For Admin

**Thai (Email Subject)**
```
[GEPP] สรุปรายการประจำวัน - {report_date}
```

**Thai (Email Body)**
```
เรียน ผู้ดูแลระบบ,

รายงานสรุปรายการประจำวัน {report_date}:

========================================
สรุปภาพรวม
========================================
รายการทั้งหมด: {total_count} รายการ
น้ำหนักรวม: {total_weight_kg} กก.
มูลค่ารวม: {total_amount_thb} บาท

========================================
แยกตามประเภทวัสดุ
========================================
{material_breakdown}

========================================
แยกตามสาขา
========================================
{location_breakdown}

========================================
สถานะรายการ
========================================
- รอตรวจสอบ: {pending_count} รายการ
- อนุมัติ: {approved_count} รายการ
- ไม่อนุมัติ: {rejected_count} รายการ

========================================
เปรียบเทียบกับวันก่อน
========================================
{comparison_with_previous}

คลิกเพื่อดูรายงานเต็ม: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Email Subject)**
```
[GEPP] Daily Transaction Summary - {report_date}
```

#### For Data Inputter (Own Transactions)

**Thai (Email Subject)**
```
[GEPP] สรุปรายการของคุณประจำวัน - {report_date}
```

**Thai (Email Body)**
```
เรียน {user_name},

รายงานสรุปรายการของคุณ วันที่ {report_date}:

========================================
สรุปรายการของคุณ
========================================
รายการที่สร้าง: {your_created_count} รายการ
น้ำหนักรวม: {your_total_weight_kg} กก.
มูลค่ารวม: {your_total_amount_thb} บาท

========================================
สถานะรายการของคุณ
========================================
- รอตรวจสอบ: {your_pending_count} รายการ
- อนุมัติ: {your_approved_count} รายการ
- ไม่อนุมัติ: {your_rejected_count} รายการ

{your_transactions_list}

คลิกเพื่อดูรายละเอียด: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

---

### RPT_TXN_WEEKLY - Weekly Transaction Summary

#### For Admin, Auditor, Viewer

**Thai (Email Subject)**
```
[GEPP] สรุปรายการประจำสัปดาห์ - {date_range}
```

**Thai (Email Body)**
```
เรียน {user_name},

รายงานสรุปรายการประจำสัปดาห์ ({date_range}):

========================================
สรุปภาพรวมสัปดาห์
========================================
รายการทั้งหมด: {total_count} รายการ
น้ำหนักรวม: {total_weight_kg} กก.
มูลค่ารวม: {total_amount_thb} บาท

========================================
แนวโน้มรายวัน
========================================
{daily_trend}

========================================
แยกตามประเภทวัสดุ
========================================
{material_breakdown}

========================================
สาขาที่มีผลงานดีที่สุด
========================================
{top_locations}

========================================
สรุปการตรวจสอบ
========================================
- AI ตรวจสอบ: {ai_audit_count} รายการ
- ตรวจสอบด้วยตนเอง: {manual_audit_count} รายการ
- อัตราอนุมัติ: {approval_rate}%

========================================
เปรียบเทียบกับสัปดาห์ก่อน
========================================
{comparison_with_previous_week}

คลิกเพื่อดูรายงานเต็ม: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

---

### RPT_TXN_MONTHLY - Monthly Transaction Summary

#### For All Recipients

**Thai (Email Subject)**
```
[GEPP] สรุปรายการประจำเดือน - {month_year}
```

**Thai (Email Body)**
```
เรียน {user_name},

รายงานสรุปรายการประจำเดือน {month_year}:

========================================
สรุปภาพรวมเดือน
========================================
รายการทั้งหมด: {total_count} รายการ
น้ำหนักรวม: {total_weight_kg} กก.
มูลค่ารวม: {total_amount_thb} บาท
ค่าเฉลี่ยต่อวัน: {daily_average_count} รายการ

========================================
แยกตามประเภทวัสดุ
========================================
{material_breakdown}

========================================
แยกตามสาขา
========================================
{location_breakdown}

========================================
แนวโน้มรายสัปดาห์
========================================
{weekly_trend}

========================================
วัสดุที่มีปริมาณสูงสุด 5 อันดับ
========================================
{top_5_materials}

========================================
การวิเคราะห์ต้นทุน
========================================
- ต้นทุนรวม: {total_cost} บาท
- ต้นทุนเฉลี่ยต่อกก.: {cost_per_kg} บาท
- เปรียบเทียบกับเดือนก่อน: {cost_comparison}

========================================
เปรียบเทียบ Year-over-Year
========================================
{year_over_year_comparison}

คลิกเพื่อดูรายงานเต็ม: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

---

### RPT_ENV_MONTHLY - Monthly Environmental Impact

#### For Admin, Auditor, Viewer

**Thai (Email Subject)**
```
[GEPP] รายงานผลกระทบสิ่งแวดล้อม - {month_year}
```

**Thai (Email Body)**
```
เรียน {user_name},

รายงานผลกระทบสิ่งแวดล้อมประจำเดือน {month_year}:

========================================
ผลกระทบสิ่งแวดล้อม
========================================
ลดการปล่อยก๊าซเรือนกระจก: {ghg_reduction_kgco2e} KGCO2E
อัตราการรีไซเคิล: {recycling_rate}%
ขยะที่หันเหจากฝังกลบ: {waste_diverted_kg} กก.

========================================
คะแนนผลกระทบสิ่งแวดล้อม
========================================
คะแนนรวม: {environmental_score}/100
- การลดขยะ: {waste_reduction_score}/25
- การรีไซเคิล: {recycling_score}/25
- การลด GHG: {ghg_score}/25
- การปฏิบัติตาม: {compliance_score}/25

========================================
เปรียบเทียบกับเป้าหมาย
========================================
{targets_comparison}

========================================
สถานะการปฏิบัติตาม GRI 306
========================================
{gri_306_status}

========================================
คำแนะนำเพื่อการปรับปรุง
========================================
{recommendations}

คลิกเพื่อดูรายงานเต็ม: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

---

### RPT_PENDING_REMINDER - Pending Transactions Reminder

#### For Admin, Auditor

**Thai (Bell)**
```
รายการรอดำเนินการ: {pending_count} รายการ
รายการที่รอนานที่สุด: {oldest_days} วัน
กรุณาตรวจสอบโดยเร็ว
```

**Thai (Email Subject)**
```
[GEPP] เตือน: รายการรอดำเนินการ {pending_count} รายการ
```

**Thai (Email Body)**
```
เรียน {user_name},

มีรายการที่รอการดำเนินการ:

========================================
สรุปรายการรอดำเนินการ
========================================
รายการรอตรวจสอบทั้งหมด: {pending_count} รายการ
รายการที่รอนานที่สุด: {oldest_days} วัน
รายการที่รอ > 7 วัน: {old_pending_count} รายการ

========================================
รายการที่ต้องดำเนินการด่วน
========================================
{urgent_transactions_list}

========================================
แยกตามสาขา
========================================
{pending_by_location}

กรุณาตรวจสอบและดำเนินการโดยเร็ว
คลิกเพื่อตรวจสอบ: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

**English (Bell)**
```
Pending Transactions: {pending_count}
Oldest: {oldest_days} days
Please review soon
```

#### For Data Inputter (Own Pending)

**Thai (Bell)**
```
รายการของคุณรอดำเนินการ: {your_pending_count} รายการ
รายการที่รอนานที่สุด: {your_oldest_days} วัน
```

**Thai (Email Subject)**
```
[GEPP] รายการของคุณรอดำเนินการ {your_pending_count} รายการ
```

**English (Bell)**
```
Your Pending Transactions: {your_pending_count}
Oldest: {your_oldest_days} days
```

---

### RPT_AUDIT_SUMMARY - Audit Completion Summary

#### For Admin, Auditor

**Thai (Email Subject)**
```
[GEPP] สรุปผลการตรวจสอบ - {date_range}
```

**Thai (Email Body)**
```
เรียน {user_name},

รายงานสรุปผลการตรวจสอบ ({date_range}):

========================================
สรุปการตรวจสอบ
========================================
รายการที่ตรวจสอบทั้งหมด: {total_audited} รายการ
- อนุมัติ: {approved_count} รายการ ({approved_rate}%)
- ไม่อนุมัติ: {rejected_count} รายการ ({rejected_rate}%)
- รอตรวจสอบ: {pending_count} รายการ

========================================
วิธีการตรวจสอบ
========================================
- AI ตรวจสอบ: {ai_audit_count} รายการ
- ตรวจสอบด้วยตนเอง: {manual_audit_count} รายการ

========================================
ข้อผิดพลาดที่พบบ่อย
========================================
{common_violations}

========================================
ประสิทธิภาพ AI
========================================
- ความแม่นยำ: {ai_accuracy}%
- อัตราข้อผิดพลาด: {ai_error_rate}%
- คะแนนความมั่นใจเฉลี่ย: {avg_confidence_score}%

========================================
แนวโน้มรายวัน
========================================
{daily_audit_trend}

คลิกเพื่อดูรายงานเต็ม: {link}

ขอบคุณ,
ระบบ GEPP Platform
```

---

## Email Templates

### Standard Email Layout

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{email_title}</title>
    <style>
        body {
            font-family: 'Noto Sans Thai', Arial, sans-serif;
            line-height: 1.6;
            color: #333333;
            background-color: #f4f4f4;
            margin: 0;
            padding: 0;
        }
        .container {
            max-width: 600px;
            margin: 20px auto;
            background-color: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .header {
            background: linear-gradient(135deg, #065f46 0%, #047857 50%, #059669 100%);
            color: #ffffff;
            padding: 20px;
            text-align: center;
        }
        .header img {
            height: 40px;
        }
        .content {
            padding: 30px;
        }
        .button {
            display: inline-block;
            background: linear-gradient(135deg, #065f46 0%, #047857 100%);
            color: #ffffff;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 6px;
            margin: 20px 0;
        }
        .footer {
            background-color: #f0fdf4;
            padding: 20px;
            text-align: center;
            color: #666666;
            font-size: 12px;
        }
        .highlight-box {
            background-color: #f0fdf4;
            border-left: 4px solid #10b981;
            padding: 15px;
            margin: 15px 0;
        }
        .warning-box {
            background-color: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 15px;
            margin: 15px 0;
        }
        .error-box {
            background-color: #fef2f2;
            border-left: 4px solid #ef4444;
            padding: 15px;
            margin: 15px 0;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
        }
        th {
            background-color: #f0fdf4;
            color: #065f46;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="https://app.gepp.com/logo.png" alt="GEPP Logo">
            <h1>{email_title}</h1>
        </div>
        <div class="content">
            {email_content}

            <a href="{action_link}" class="button">{action_text}</a>
        </div>
        <div class="footer">
            <p>GEPP Platform - Environmental Sustainability Management</p>
            <p>หากคุณไม่ต้องการรับอีเมลนี้ กรุณา<a href="{unsubscribe_link}">ยกเลิกการรับข่าวสาร</a></p>
            <p>&copy; 2026 GEPP. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
```

---

## Bell Notification Templates

### Standard Bell Notification Format

```json
{
  "id": "notification_uuid",
  "type": "bell",
  "event_code": "TXN_APPROVED",
  "title": "รายการได้รับอนุมัติ",
  "message": "รายการ {transaction_id} ได้รับการอนุมัติแล้ว",
  "icon": "check-circle",
  "icon_color": "#10b981",
  "data": {
    "transaction_id": 12345,
    "link": "/transactions/12345"
  },
  "is_read": false,
  "created_at": "2026-01-27T10:30:00Z"
}
```

### Notification Icon Mapping

| Event Type | Icon | Color |
|------------|------|-------|
| Transaction Created | `plus-circle` | `#3b82f6` |
| Transaction Approved | `check-circle` | `#10b981` |
| Transaction Rejected | `close-circle` | `#ef4444` |
| Transaction Pending | `clock-circle` | `#f59e0b` |
| Audit Violation | `warning` | `#ef4444` |
| AI Audit Complete | `robot` | `#9ac7b5` |
| Organization Update | `apartment` | `#6366f1` |
| Location Update | `environment` | `#8b5cf6` |
| User Added | `user-add` | `#10b981` |
| Role Changed | `swap` | `#f59e0b` |
| System Maintenance | `tool` | `#6b7280` |
| Report Available | `file-text` | `#3b82f6` |

---

## Message Priority Levels

| Priority | Level | Use Case |
|----------|-------|----------|
| 1 | Critical | Security alerts, system failures, urgent compliance issues |
| 2 | High | Audit violations, rejected transactions, pending reminders |
| 3 | Normal | Standard transactions, approvals, updates |
| 4 | Low | Reports, informational updates, new features |

---

## Localization Notes

### Thai Date Format
- Short: `27/01/2569`
- Long: `27 มกราคม 2569`
- Range: `1-31 ม.ค. 2569`

### Thai Number Format
- Currency: `2,500.00 บาท`
- Weight: `150.5 กก.`
- Percentage: `85.5%`

### Time Format
- 24-hour: `14:30`
- With period: `14:30 น.`

---

## Summary

This document provides comprehensive notification message templates for:

1. **All Event Types**: Transaction, Organization, Location, User, and System events
2. **All Roles**: Admin, Data Inputter, Auditor, and Viewer
3. **All Channels**: Email and Bell (in-app) notifications
4. **All Languages**: Thai and English versions
5. **All Report Types**: Daily, Weekly, Bi-weekly, and Monthly summaries

Each message template includes:
- Subject/title for easy identification
- Body content with variable placeholders
- Appropriate formatting and layout
- Action links for user engagement

---

**Document Version**: 1.0.0
**Last Updated**: January 27, 2026
**Author**: GEPP Platform Team
