# Notification Role Scheduler Design Document

**Version**: 1.0.0
**Created Date**: January 27, 2026
**Status**: Design Phase

---

## Overview

This document defines the comprehensive notification system design for the GEPP Platform. The notification system combines **Email** and **In-App Bell Notifications** to ensure users receive timely updates based on their roles and preferences.

---

## Table of Contents

1. [Organization Roles](#organization-roles)
2. [Notification Types](#notification-types)
3. [Action Notifications (Event-Triggered)](#action-notifications-event-triggered)
4. [Report Notifications (Scheduled)](#report-notifications-scheduled)
5. [Role-Based Permission Matrix](#role-based-permission-matrix)
6. [Frequency Configuration](#frequency-configuration)
7. [Notification Settings UI Mockup](#notification-settings-ui-mockup)
8. [Database Schema](#database-schema)
9. [Implementation Notes](#implementation-notes)

---

## Organization Roles

| Role Key | Thai Name | English Name | Description |
|----------|-----------|--------------|-------------|
| `admin` | ผู้ดูแลระบบ | Administrator | Full system access, can manage all settings and users |
| `data_inputter` | ผู้บันทึกข้อมูล | Data Inputter | Can create and update transactions, view their own data |
| `auditor` | ผู้ตรวจสอบ | Auditor | Can review, approve, or reject transactions |
| `viewer` | ผู้ชม | Viewer | Read-only access to reports and data |

---

## Notification Types

### 1. Action Notifications (Event-Triggered)
Notifications triggered immediately when specific events occur in the system.

### 2. Report Notifications (Scheduled)
Periodic summary notifications sent at configured intervals.

---

## Action Notifications (Event-Triggered)

### Category A: Transaction Events

| Event Code | Event Name (EN) | Event Name (TH) | Description |
|------------|-----------------|-----------------|-------------|
| `TXN_CREATED` | Transaction Created | สร้างรายการใหม่ | A new transaction has been created |
| `TXN_UPDATED` | Transaction Updated | อัปเดตรายการ | An existing transaction has been modified |
| `TXN_DELETED` | Transaction Deleted | ลบรายการ | A transaction has been deleted |
| `TXN_SUBMITTED` | Transaction Submitted | ส่งรายการตรวจสอบ | Transaction submitted for review |
| `TXN_APPROVED` | Transaction Approved | อนุมัติรายการ | Transaction has been approved |
| `TXN_REJECTED` | Transaction Rejected | ปฏิเสธรายการ | Transaction has been rejected |
| `TXN_PENDING_REVIEW` | Pending Review | รอการตรวจสอบ | Transaction is waiting for review |
| `TXN_AI_AUDIT_COMPLETED` | AI Audit Completed | ตรวจสอบด้วย AI เสร็จสิ้น | AI audit process completed |
| `TXN_MANUAL_AUDIT_COMPLETED` | Manual Audit Completed | ตรวจสอบด้วยตนเองเสร็จสิ้น | Manual audit process completed |

### Category B: Organization Events

| Event Code | Event Name (EN) | Event Name (TH) | Description |
|------------|-----------------|-----------------|-------------|
| `ORG_UPDATED` | Organization Updated | อัปเดตข้อมูลองค์กร | Organization settings updated |
| `ORG_CHART_UPDATED` | Org Chart Updated | อัปเดตผังองค์กร | Organization structure changed |
| `ORG_SETTINGS_CHANGED` | Settings Changed | เปลี่ยนการตั้งค่า | Organization settings modified |

### Category C: Location Events

| Event Code | Event Name (EN) | Event Name (TH) | Description |
|------------|-----------------|-----------------|-------------|
| `LOC_CREATED` | Location Created | สร้างสาขาใหม่ | New location added |
| `LOC_UPDATED` | Location Updated | อัปเดตสาขา | Location details updated |
| `LOC_DELETED` | Location Deleted | ลบสาขา | Location removed |
| `LOC_TAG_CREATED` | Location Tag Created | สร้างแท็กสาขา | New tag assigned to location |
| `LOC_TAG_UPDATED` | Location Tag Updated | อัปเดตแท็กสาขา | Location tag modified |

### Category D: User & Member Events

| Event Code | Event Name (EN) | Event Name (TH) | Description |
|------------|-----------------|-----------------|-------------|
| `USER_ADDED` | User Added | เพิ่มผู้ใช้ใหม่ | New user added to organization |
| `USER_REMOVED` | User Removed | ลบผู้ใช้ | User removed from organization |
| `USER_ROLE_CHANGED` | Role Changed | เปลี่ยนบทบาท | User's role has been changed |
| `USER_LOCATION_ASSIGNED` | Location Assigned | มอบหมายสาขา | User assigned to location |
| `USER_LOCATION_REMOVED` | Location Unassigned | ยกเลิกการมอบหมาย | User unassigned from location |

### Category E: System Events

| Event Code | Event Name (EN) | Event Name (TH) | Description |
|------------|-----------------|-----------------|-------------|
| `SYS_MAINTENANCE` | System Maintenance | ปิดปรับปรุงระบบ | Scheduled system maintenance |
| `SYS_UPDATE` | System Update | อัปเดตระบบ | New system features available |
| `SYS_ALERT` | System Alert | แจ้งเตือนระบบ | Important system notification |

---

## Report Notifications (Scheduled)

### Report Categories

| Report Code | Report Name (EN) | Report Name (TH) | Description |
|-------------|------------------|------------------|-------------|
| `RPT_TXN_DAILY` | Daily Transaction Summary | สรุปรายการประจำวัน | Daily summary of all transactions |
| `RPT_TXN_WEEKLY` | Weekly Transaction Summary | สรุปรายการประจำสัปดาห์ | 7-day transaction summary |
| `RPT_TXN_BIWEEKLY` | Bi-weekly Transaction Summary | สรุปรายการ 14 วัน | 14-day transaction summary |
| `RPT_TXN_MONTHLY` | Monthly Transaction Summary | สรุปรายการประจำเดือน | Monthly transaction summary |
| `RPT_ENV_MONTHLY` | Monthly Environmental Impact | ผลกระทบสิ่งแวดล้อมประจำเดือน | Monthly GHG reduction report |
| `RPT_PENDING_REMINDER` | Pending Transactions Reminder | รายการที่รอดำเนินการ | Reminder of pending transactions |
| `RPT_AUDIT_SUMMARY` | Audit Completion Summary | สรุปผลการตรวจสอบ | Audit results summary |
| `RPT_WASTE_ANALYTICS` | Waste Analytics Report | รายงานวิเคราะห์ของเสีย | Detailed waste analytics |
| `RPT_LOCATION_PERFORMANCE` | Location Performance | ผลประกอบการสาขา | Per-location performance metrics |
| `RPT_COMPLIANCE_STATUS` | Compliance Status Report | สถานะการปฏิบัติตามกฎหมาย | GRI 306 compliance status |

### Available Frequencies

| Frequency Code | Frequency Name (EN) | Frequency Name (TH) | Interval |
|----------------|---------------------|---------------------|----------|
| `REALTIME` | Real-time | ทันที | Immediate |
| `DAILY` | Daily | รายวัน | Every 24 hours |
| `WEEKLY` | Weekly (7 days) | รายสัปดาห์ | Every 7 days |
| `BIWEEKLY` | Bi-weekly (14 days) | ทุก 14 วัน | Every 14 days |
| `MONTHLY` | Monthly | รายเดือน | Every 30 days |
| `OFF` | Disabled | ปิด | No notification |

---

## Role-Based Permission Matrix

### Action Notifications - Who Receives What

#### Transaction Events

| Event | Admin | Data Inputter | Auditor | Viewer |
|-------|-------|---------------|---------|--------|
| `TXN_CREATED` | Email + Bell | Bell (own) | Bell | - |
| `TXN_UPDATED` | Email + Bell | Bell (own) | Bell | - |
| `TXN_DELETED` | Email + Bell | Bell (own) | - | - |
| `TXN_SUBMITTED` | Bell | - | Email + Bell | - |
| `TXN_APPROVED` | Bell | Email + Bell (own) | Bell | Bell |
| `TXN_REJECTED` | Bell | Email + Bell (own) | Bell | - |
| `TXN_PENDING_REVIEW` | Bell | Bell (own) | Email + Bell | - |
| `TXN_AI_AUDIT_COMPLETED` | Email + Bell | Bell (own) | Email + Bell | - |
| `TXN_MANUAL_AUDIT_COMPLETED` | Email + Bell | Bell (own) | Email + Bell | - |

**Legend:**
- `Email + Bell`: Both email and in-app notification
- `Bell`: In-app notification only
- `Bell (own)`: Only for transactions created by this user
- `-`: No notification

#### Organization Events

| Event | Admin | Data Inputter | Auditor | Viewer |
|-------|-------|---------------|---------|--------|
| `ORG_UPDATED` | Email + Bell | - | - | - |
| `ORG_CHART_UPDATED` | Email + Bell | Bell | Bell | Bell |
| `ORG_SETTINGS_CHANGED` | Email + Bell | - | - | - |

#### Location Events

| Event | Admin | Data Inputter | Auditor | Viewer |
|-------|-------|---------------|---------|--------|
| `LOC_CREATED` | Email + Bell | Bell | Bell | - |
| `LOC_UPDATED` | Email + Bell | Bell (assigned) | Bell (assigned) | - |
| `LOC_DELETED` | Email + Bell | Bell (assigned) | Bell (assigned) | - |
| `LOC_TAG_CREATED` | Bell | Bell (assigned) | Bell (assigned) | - |
| `LOC_TAG_UPDATED` | Bell | Bell (assigned) | Bell (assigned) | - |

#### User & Member Events

| Event | Admin | Data Inputter | Auditor | Viewer |
|-------|-------|---------------|---------|--------|
| `USER_ADDED` | Email + Bell | - | - | - |
| `USER_REMOVED` | Email + Bell | - | - | - |
| `USER_ROLE_CHANGED` | Email + Bell | Email (self) | Email (self) | Email (self) |
| `USER_LOCATION_ASSIGNED` | Email + Bell | Email (self) | Email (self) | Email (self) |
| `USER_LOCATION_REMOVED` | Email + Bell | Email (self) | Email (self) | Email (self) |

#### System Events

| Event | Admin | Data Inputter | Auditor | Viewer |
|-------|-------|---------------|---------|--------|
| `SYS_MAINTENANCE` | Email + Bell | Email + Bell | Email + Bell | Email + Bell |
| `SYS_UPDATE` | Email + Bell | Bell | Bell | Bell |
| `SYS_ALERT` | Email + Bell | Bell | Bell | Bell |

---

### Report Notifications - Who Receives What

#### Default Frequency by Role

| Report | Admin | Data Inputter | Auditor | Viewer |
|--------|-------|---------------|---------|--------|
| `RPT_TXN_DAILY` | Email | Email (own) | Email | - |
| `RPT_TXN_WEEKLY` | Email | - | Email | Email |
| `RPT_TXN_BIWEEKLY` | Email | - | Email | Email |
| `RPT_TXN_MONTHLY` | Email | Email | Email | Email |
| `RPT_ENV_MONTHLY` | Email | - | Email | Email |
| `RPT_PENDING_REMINDER` | Email + Bell | Email + Bell (own) | Email + Bell | - |
| `RPT_AUDIT_SUMMARY` | Email | - | Email | Email |
| `RPT_WASTE_ANALYTICS` | Email | - | - | Email |
| `RPT_LOCATION_PERFORMANCE` | Email | - | - | Email |
| `RPT_COMPLIANCE_STATUS` | Email | - | - | Email |

#### Available Frequency Options by Report

| Report | Real-time | Daily | Weekly | Bi-weekly | Monthly | Off |
|--------|-----------|-------|--------|-----------|---------|-----|
| `RPT_TXN_DAILY` | - | Yes (default) | - | - | - | Yes |
| `RPT_TXN_WEEKLY` | - | - | Yes (default) | - | - | Yes |
| `RPT_TXN_BIWEEKLY` | - | - | - | Yes (default) | - | Yes |
| `RPT_TXN_MONTHLY` | - | - | - | - | Yes (default) | Yes |
| `RPT_ENV_MONTHLY` | - | - | - | - | Yes (default) | Yes |
| `RPT_PENDING_REMINDER` | - | Yes (default) | Yes | - | - | Yes |
| `RPT_AUDIT_SUMMARY` | - | Yes | Yes (default) | Yes | Yes | Yes |
| `RPT_WASTE_ANALYTICS` | - | - | Yes | Yes | Yes (default) | Yes |
| `RPT_LOCATION_PERFORMANCE` | - | - | Yes | Yes | Yes (default) | Yes |
| `RPT_COMPLIANCE_STATUS` | - | - | - | - | Yes (default) | Yes |

---

## Frequency Configuration

### Detailed Frequency Specifications

#### Transaction Summary Reports

```yaml
RPT_TXN_DAILY:
  name: "Daily Transaction Summary"
  name_th: "สรุปรายการประจำวัน"
  available_frequencies: ["DAILY", "OFF"]
  default_frequency: "DAILY"
  delivery_time: "08:00"  # Local time
  content:
    - total_transactions_count
    - total_weight_kg
    - total_amount_thb
    - breakdown_by_material_type
    - breakdown_by_location
    - comparison_with_previous_day
  recipients:
    admin: { email: true, bell: false }
    data_inputter: { email: true, bell: false, scope: "own_transactions" }
    auditor: { email: true, bell: false }
    viewer: { email: false, bell: false }

RPT_TXN_WEEKLY:
  name: "Weekly Transaction Summary"
  name_th: "สรุปรายการประจำสัปดาห์"
  available_frequencies: ["WEEKLY", "OFF"]
  default_frequency: "WEEKLY"
  delivery_day: "Monday"
  delivery_time: "08:00"
  content:
    - total_transactions_count
    - total_weight_kg
    - total_amount_thb
    - breakdown_by_material_type
    - breakdown_by_location
    - daily_trend_chart_data
    - top_performing_locations
    - comparison_with_previous_week
  recipients:
    admin: { email: true, bell: false }
    data_inputter: { email: false, bell: false }
    auditor: { email: true, bell: false }
    viewer: { email: true, bell: false }

RPT_TXN_BIWEEKLY:
  name: "Bi-weekly Transaction Summary"
  name_th: "สรุปรายการ 14 วัน"
  available_frequencies: ["BIWEEKLY", "OFF"]
  default_frequency: "BIWEEKLY"
  delivery_day: "Monday"  # Every other Monday
  delivery_time: "08:00"
  content:
    - total_transactions_count
    - total_weight_kg
    - total_amount_thb
    - breakdown_by_material_type
    - breakdown_by_location
    - trend_analysis
    - comparison_with_previous_period
  recipients:
    admin: { email: true, bell: false }
    data_inputter: { email: false, bell: false }
    auditor: { email: true, bell: false }
    viewer: { email: true, bell: false }

RPT_TXN_MONTHLY:
  name: "Monthly Transaction Summary"
  name_th: "สรุปรายการประจำเดือน"
  available_frequencies: ["MONTHLY", "OFF"]
  default_frequency: "MONTHLY"
  delivery_day: 1  # First day of month
  delivery_time: "08:00"
  content:
    - total_transactions_count
    - total_weight_kg
    - total_amount_thb
    - breakdown_by_material_type
    - breakdown_by_location
    - monthly_trend_chart_data
    - year_over_year_comparison
    - top_materials_by_volume
    - cost_analysis
  recipients:
    admin: { email: true, bell: false }
    data_inputter: { email: true, bell: false }
    auditor: { email: true, bell: false }
    viewer: { email: true, bell: false }
```

#### Environmental & Compliance Reports

```yaml
RPT_ENV_MONTHLY:
  name: "Monthly Environmental Impact"
  name_th: "ผลกระทบสิ่งแวดล้อมประจำเดือน"
  available_frequencies: ["MONTHLY", "OFF"]
  default_frequency: "MONTHLY"
  delivery_day: 1
  delivery_time: "08:00"
  content:
    - total_ghg_reduction_kgco2e
    - recycling_rate_percentage
    - waste_diverted_from_landfill
    - environmental_impact_score
    - comparison_with_targets
    - gri_306_compliance_status
  recipients:
    admin: { email: true, bell: false }
    data_inputter: { email: false, bell: false }
    auditor: { email: true, bell: false }
    viewer: { email: true, bell: false }

RPT_COMPLIANCE_STATUS:
  name: "Compliance Status Report"
  name_th: "สถานะการปฏิบัติตามกฎหมาย"
  available_frequencies: ["MONTHLY", "OFF"]
  default_frequency: "MONTHLY"
  delivery_day: 1
  delivery_time: "08:00"
  content:
    - gri_306_compliance_score
    - epr_compliance_status
    - pending_compliance_items
    - upcoming_deadlines
    - recommendations
  recipients:
    admin: { email: true, bell: false }
    data_inputter: { email: false, bell: false }
    auditor: { email: false, bell: false }
    viewer: { email: true, bell: false }
```

#### Reminder & Alert Reports

```yaml
RPT_PENDING_REMINDER:
  name: "Pending Transactions Reminder"
  name_th: "รายการที่รอดำเนินการ"
  available_frequencies: ["DAILY", "WEEKLY", "OFF"]
  default_frequency: "DAILY"
  delivery_time: "09:00"
  threshold:
    pending_age_days: 3  # Only remind if pending > 3 days
    min_count: 1         # Only send if at least 1 pending
  content:
    - pending_transactions_list
    - pending_transactions_count
    - oldest_pending_date
    - pending_by_status
    - action_required_items
  recipients:
    admin: { email: true, bell: true }
    data_inputter: { email: true, bell: true, scope: "own_transactions" }
    auditor: { email: true, bell: true }
    viewer: { email: false, bell: false }

RPT_AUDIT_SUMMARY:
  name: "Audit Completion Summary"
  name_th: "สรุปผลการตรวจสอบ"
  available_frequencies: ["DAILY", "WEEKLY", "BIWEEKLY", "MONTHLY", "OFF"]
  default_frequency: "WEEKLY"
  delivery_day: "Monday"
  delivery_time: "08:00"
  content:
    - total_audited_count
    - approved_count
    - rejected_count
    - pending_audit_count
    - ai_audit_count
    - manual_audit_count
    - common_violation_types
    - audit_accuracy_metrics
  recipients:
    admin: { email: true, bell: false }
    data_inputter: { email: false, bell: false }
    auditor: { email: true, bell: false }
    viewer: { email: true, bell: false }
```

---

## Notification Settings UI Mockup

### Location Settings → Notification Tab

```
┌─────────────────────────────────────────────────────────────────────┐
│  จัดการองค์กร (Locations)                                           │
├─────────────────────────────────────────────────────────────────────┤
│  [QR Input]  [Notification]  [Other Settings...]                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  การแจ้งเตือนรายการ (Transaction Notifications)              │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │                                                             │   │
│  │  ┌─ หมวดหมู่ A: เหตุการณ์รายการ ─────────────────────────┐ │   │
│  │  │                                                         │ │   │
│  │  │  สร้างรายการใหม่ (Transaction Created)                  │ │   │
│  │  │  ├─ Email: [v] Admin  [ ] Data Inputter  [ ] Auditor   │ │   │
│  │  │  └─ Bell:  [v] Admin  [v] Data Inputter  [v] Auditor   │ │   │
│  │  │                                                         │ │   │
│  │  │  อนุมัติรายการ (Transaction Approved)                   │ │   │
│  │  │  ├─ Email: [ ] Admin  [v] Data Inputter  [ ] Auditor   │ │   │
│  │  │  └─ Bell:  [v] Admin  [v] Data Inputter  [v] Auditor   │ │   │
│  │  │                                                         │ │   │
│  │  │  ปฏิเสธรายการ (Transaction Rejected)                    │ │   │
│  │  │  ├─ Email: [ ] Admin  [v] Data Inputter  [ ] Auditor   │ │   │
│  │  │  └─ Bell:  [v] Admin  [v] Data Inputter  [v] Auditor   │ │   │
│  │  │                                                         │ │   │
│  │  └─────────────────────────────────────────────────────────┘ │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  รายงานสรุป (Report Notifications)                          │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │                                                             │   │
│  │  สรุปรายการประจำวัน (Daily Summary)                         │   │
│  │  ├─ ความถี่: [รายวัน  v]  เวลา: [08:00 v]                  │   │
│  │  ├─ Email: [v] Admin  [v] Data Inputter  [v] Auditor       │   │
│  │  └─ สถานะ: เปิดใช้งาน                                       │   │
│  │                                                             │   │
│  │  สรุปรายการประจำสัปดาห์ (Weekly Summary)                    │   │
│  │  ├─ ความถี่: [รายสัปดาห์  v]  วัน: [จันทร์ v] เวลา: [08:00 v] │   │
│  │  ├─ Email: [v] Admin  [ ] Data Inputter  [v] Auditor       │   │
│  │  └─ สถานะ: เปิดใช้งาน                                       │   │
│  │                                                             │   │
│  │  สรุปรายการ 14 วัน (Bi-weekly Summary)                      │   │
│  │  ├─ ความถี่: [ทุก 14 วัน  v]  เวลา: [08:00 v]              │   │
│  │  ├─ Email: [v] Admin  [ ] Data Inputter  [v] Auditor       │   │
│  │  └─ สถานะ: เปิดใช้งาน                                       │   │
│  │                                                             │   │
│  │  สรุปรายการประจำเดือน (Monthly Summary)                     │   │
│  │  ├─ ความถี่: [รายเดือน  v]  วันที่: [1 v] เวลา: [08:00 v]  │   │
│  │  ├─ Email: [v] Admin  [v] Data Inputter  [v] Auditor       │   │
│  │  └─ สถานะ: เปิดใช้งาน                                       │   │
│  │                                                             │   │
│  │  รายการที่รอดำเนินการ (Pending Reminder)                    │   │
│  │  ├─ ความถี่: [รายวัน  v]  เวลา: [09:00 v]                  │   │
│  │  ├─ Email: [v] Admin  [v] Data Inputter  [v] Auditor       │   │
│  │  ├─ Bell:  [v] Admin  [v] Data Inputter  [v] Auditor       │   │
│  │  ├─ เตือนเมื่อรอนานกว่า: [3 วัน v]                         │   │
│  │  └─ สถานะ: เปิดใช้งาน                                       │   │
│  │                                                             │   │
│  │  ผลกระทบสิ่งแวดล้อมประจำเดือน (Environmental Impact)        │   │
│  │  ├─ ความถี่: [รายเดือน  v]  วันที่: [1 v] เวลา: [08:00 v]  │   │
│  │  ├─ Email: [v] Admin  [ ] Data Inputter  [v] Auditor       │   │
│  │  └─ สถานะ: เปิดใช้งาน                                       │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  การแจ้งเตือนระบบ (System Notifications)                    │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │                                                             │   │
│  │  อัปเดตผังองค์กร (Organization Chart Updated)               │   │
│  │  ├─ Email: [v] Admin  [ ] Data Inputter  [ ] Auditor       │   │
│  │  └─ Bell:  [v] Admin  [v] Data Inputter  [v] Auditor       │   │
│  │                                                             │   │
│  │  เพิ่มผู้ใช้ใหม่ (User Added)                               │   │
│  │  ├─ Email: [v] Admin                                        │   │
│  │  └─ Bell:  [v] Admin                                        │   │
│  │                                                             │   │
│  │  เปลี่ยนบทบาท (Role Changed)                                │   │
│  │  ├─ Email: [v] Admin  [v] ผู้ใช้ที่เกี่ยวข้อง               │   │
│  │  └─ Bell:  [v] Admin  [v] ผู้ใช้ที่เกี่ยวข้อง               │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│                                    [ยกเลิก]  [บันทึกการตั้งค่า]     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Tables Required

```sql
-- Notification Settings Table
CREATE TABLE notification_settings (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    event_code VARCHAR(50) NOT NULL,

    -- Role-based settings (JSONB for flexibility)
    admin_email BOOLEAN DEFAULT FALSE,
    admin_bell BOOLEAN DEFAULT FALSE,
    data_inputter_email BOOLEAN DEFAULT FALSE,
    data_inputter_bell BOOLEAN DEFAULT FALSE,
    auditor_email BOOLEAN DEFAULT FALSE,
    auditor_bell BOOLEAN DEFAULT FALSE,
    viewer_email BOOLEAN DEFAULT FALSE,
    viewer_bell BOOLEAN DEFAULT FALSE,

    -- For report notifications
    frequency VARCHAR(20), -- REALTIME, DAILY, WEEKLY, BIWEEKLY, MONTHLY, OFF
    delivery_time TIME DEFAULT '08:00:00',
    delivery_day_of_week INTEGER, -- 0=Sunday, 1=Monday, etc.
    delivery_day_of_month INTEGER, -- 1-31

    -- Additional settings
    threshold_config JSONB, -- For configurable thresholds

    is_active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMPTZ DEFAULT NOW(),
    updated_date TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(organization_id, event_code)
);

-- Notification Log Table
CREATE TABLE notification_logs (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    user_id BIGINT REFERENCES user_locations(id),
    event_code VARCHAR(50) NOT NULL,
    notification_type VARCHAR(20) NOT NULL, -- 'email' or 'bell'

    -- Content
    title VARCHAR(500) NOT NULL,
    message TEXT NOT NULL,
    data JSONB, -- Additional data (transaction_id, etc.)

    -- Status
    status VARCHAR(20) DEFAULT 'pending', -- pending, sent, failed, read
    sent_at TIMESTAMPTZ,
    read_at TIMESTAMPTZ,
    error_message TEXT,

    created_date TIMESTAMPTZ DEFAULT NOW()
);

-- User Notification Preferences (Override org defaults)
CREATE TABLE user_notification_preferences (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES user_locations(id) ON DELETE CASCADE,
    event_code VARCHAR(50) NOT NULL,

    email_enabled BOOLEAN DEFAULT TRUE,
    bell_enabled BOOLEAN DEFAULT TRUE,
    frequency VARCHAR(20), -- Override org frequency

    created_date TIMESTAMPTZ DEFAULT NOW(),
    updated_date TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(user_id, event_code)
);

-- Indexes
CREATE INDEX idx_notification_settings_org_id ON notification_settings(organization_id);
CREATE INDEX idx_notification_settings_event_code ON notification_settings(event_code);
CREATE INDEX idx_notification_logs_user_id ON notification_logs(user_id);
CREATE INDEX idx_notification_logs_status ON notification_logs(status);
CREATE INDEX idx_notification_logs_created_date ON notification_logs(created_date);
CREATE INDEX idx_user_notification_prefs_user_id ON user_notification_preferences(user_id);
```

---

## Implementation Notes

### 1. Event Emission Pattern

```python
# Example: When a transaction is created
class TransactionService:
    def create_transaction(self, data: dict, user_id: int) -> Transaction:
        # Create the transaction
        transaction = self._create_transaction_record(data)

        # Emit notification event
        notification_service.emit_event(
            event_code='TXN_CREATED',
            organization_id=transaction.organization_id,
            data={
                'transaction_id': transaction.id,
                'created_by_user_id': user_id,
                'transaction_date': transaction.transaction_date,
                'total_amount': transaction.total_amount,
                'location_id': transaction.user_location_id
            }
        )

        return transaction
```

### 2. Notification Processing Flow

```
1. Event Emitted
    ↓
2. Load Organization Notification Settings
    ↓
3. Determine Recipients by Role
    ↓
4. Check User Preferences (Override)
    ↓
5. Generate Notification Content
    ↓
6. Queue Notifications
    ├─ Email Queue → Email Service
    └─ Bell Queue → WebSocket/Push
    ↓
7. Log Notification Status
```

### 3. Scheduled Report Processing

```python
# Cron job scheduler example
CRON_SCHEDULE = {
    'DAILY': '0 8 * * *',      # Every day at 8:00 AM
    'WEEKLY': '0 8 * * 1',     # Every Monday at 8:00 AM
    'BIWEEKLY': '0 8 1,15 * *', # 1st and 15th of month at 8:00 AM
    'MONTHLY': '0 8 1 * *',    # 1st of month at 8:00 AM
}

async def process_scheduled_reports():
    current_time = datetime.now()

    # Get all active report settings
    settings = get_active_report_settings()

    for setting in settings:
        if should_send_now(setting, current_time):
            report_data = generate_report(setting)
            send_report_notifications(setting, report_data)
```

### 4. WebSocket for Bell Notifications

```typescript
// Frontend WebSocket connection
const notificationSocket = new WebSocket('wss://api.gepp.com/ws/notifications');

notificationSocket.onmessage = (event) => {
    const notification = JSON.parse(event.data);

    // Update bell icon badge count
    updateNotificationBadge(notification);

    // Show toast notification
    showToastNotification(notification);

    // Add to notification list
    addToNotificationList(notification);
};
```

---

## Summary

This notification system design provides:

1. **Comprehensive Coverage**: All major events in the GEPP platform trigger appropriate notifications
2. **Role-Based Delivery**: Different roles receive different notifications based on their responsibilities
3. **Flexible Frequency**: Report notifications can be configured from daily to monthly intervals
4. **Multiple Channels**: Both email and in-app (bell) notifications are supported
5. **Configurable Settings**: Organization admins can customize notification behavior
6. **User Preferences**: Individual users can override organization defaults
7. **Scalable Architecture**: Queue-based processing for reliability

---

**Document Version**: 1.0.0
**Last Updated**: January 27, 2026
**Author**: GEPP Platform Team
