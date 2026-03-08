# GEPP LINE AI Manager - Business Cost Calculator Guide

## 🎯 Quick Reference for Pricing Strategy

This guide helps you calculate **exactly how many operations** each subscription tier can support while maintaining profitability.

---

## 💰 Cost Per Operation (Fixed Prices)

| Operation Type | Cost (THB) | Icon | Notes |
|----------------|------------|------|-------|
| General Question | ฿0.007 | 💬 | Baseline (1x) |
| Summary Report | ฿0.011 | 📄 | 1.5x |
| Transaction Query | ฿0.012 | 🔍 | 1.7x |
| Transaction Insert | ฿0.010 | ➕ | 1.4x |
| GRI Report | ฿0.013 | 📊 | 1.8x |
| Image Analysis | ฿0.024 | 📸 | **3.4x (Expensive!)** |
| Chart Generation | ฿0.011 | 📈 | 1.5x |
| Alert Check | ฿0.011 | 🔔 | 1.5x |

**Average Text Operation Cost:** ฿0.011
**Average Image Operation Cost:** ฿0.024 (2.2x more expensive)

---

## 📊 Package Limit Calculator

### **Formula: How many operations can each package afford?**

```
Break-even Operations = (Package Price - Infrastructure Cost) / Avg Operation Cost
Safe Limit = Break-even Operations × 0.1  (Keep 90% profit margin)
```

### **Starter Package (฿890/month)**

```
Infrastructure Cost: ฿50/month (base)
Available Budget: ฿890 - ฿50 = ฿840

If all TEXT operations (฿0.011 each):
  Max Operations = ฿840 / ฿0.011 = 76,364 operations
  Safe Limit (90% margin) = 76,364 × 0.1 = 7,636 operations

If 50% IMAGE operations:
  Text: 3,818 ops × ฿0.011 = ฿42
  Image: 3,818 ops × ฿0.024 = ฿92
  Total: ฿134 for 7,636 operations
  Profit: ฿890 - ฿50 - ฿134 = ฿706 (79% margin)

RECOMMENDED LIMIT: 100 operations (no images)
  - All text operations: 100 × ฿0.011 = ฿1.10
  - Total cost: ฿51.10
  - Profit: ฿838.90 (94.3% margin) ✅
```

### **Pro Package (฿3,500/month)**

```
Infrastructure Cost: ฿150/month (higher tier)
Available Budget: ฿3,500 - ฿150 = ฿3,350

If all TEXT operations:
  Max Operations = ฿3,350 / ฿0.011 = 304,545 operations
  Safe Limit (90% margin) = 30,455 operations

If 25% IMAGE operations (typical Pro user):
  Text: 15,000 ops × ฿0.011 = ฿165
  Image: 5,000 ops × ฿0.024 = ฿120
  Total: ฿285 for 20,000 operations
  Profit: ฿3,500 - ฿150 - ฿285 = ฿3,065 (87.6% margin)

RECOMMENDED LIMIT: 2,000 operations (500 images max)
  - 1,500 text: 1,500 × ฿0.011 = ฿16.50
  - 500 images: 500 × ฿0.024 = ฿12.00
  - Total cost: ฿178.50
  - Profit: ฿3,321.50 (94.9% margin) ✅
```

### **Enterprise Package (฿12,000/month)**

```
Infrastructure Cost: ฿500/month (dedicated)
Available Budget: ฿12,000 - ฿500 = ฿11,500

If 20% IMAGE operations (heavy user):
  Text: 40,000 ops × ฿0.011 = ฿440
  Image: 10,000 ops × ฿0.024 = ฿240
  Total: ฿680 for 50,000 operations
  Profit: ฿12,000 - ฿500 - ฿680 = ฿10,820 (90.2% margin)

RECOMMENDED LIMIT: Unlimited (with fair use policy)
  - Estimated typical usage: 10,000 ops/month
  - Cost: ~฿170 (text + images)
  - Profit: ฿11,330 (94.4% margin) ✅
```

---

## 🧮 Calculate Your Own Pricing

### **Step 1: Decide Target Profit Margin**

```python
target_margin = 0.90  # 90% profit margin
```

### **Step 2: Calculate Operational Costs**

```python
def calculate_cost(
    price: float,
    text_operations: int,
    image_operations: int,
    infrastructure_cost: float
):
    """
    Calculate total cost and profit for a subscription tier

    Args:
        price: Monthly subscription price (THB)
        text_operations: Number of text-based operations
        image_operations: Number of image operations
        infrastructure_cost: Fixed infrastructure cost per user (THB)

    Returns:
        dict with cost breakdown and profit
    """
    text_cost = text_operations * 0.011
    image_cost = image_operations * 0.024
    total_ai_cost = text_cost + image_cost
    total_cost = total_ai_cost + infrastructure_cost

    profit = price - total_cost
    margin = (profit / price) * 100

    return {
        "price": price,
        "text_operations": text_operations,
        "image_operations": image_operations,
        "total_operations": text_operations + image_operations,
        "text_cost": text_cost,
        "image_cost": image_cost,
        "total_ai_cost": total_ai_cost,
        "infrastructure_cost": infrastructure_cost,
        "total_cost": total_cost,
        "profit": profit,
        "margin": margin
    }

# Example: Pro Package
result = calculate_cost(
    price=3500,
    text_operations=1500,
    image_operations=500,
    infrastructure_cost=150
)

print(f"Total Operations: {result['total_operations']}")
print(f"AI Cost: ฿{result['total_ai_cost']:.2f}")
print(f"Total Cost: ฿{result['total_cost']:.2f}")
print(f"Profit: ฿{result['profit']:.2f}")
print(f"Margin: {result['margin']:.1f}%")
```

**Output:**
```
Total Operations: 2000
AI Cost: ฿28.50
Total Cost: ฿178.50
Profit: ฿3321.50
Margin: 94.9%
```

---

## 📈 Usage Scenarios & Recommendations

### **Scenario 1: Light User (Starter)**

**Profile:**
- Small business owner
- Checks waste data 2-3 times per week
- Needs basic summaries

**Typical Usage (per month):**
```
70 general questions     = ฿0.49
20 summary reports       = ฿0.22
5 transaction queries    = ฿0.06
3 alert checks           = ฿0.03
2 GRI reports            = ฿0.03
0 images (not allowed)   = ฿0.00
--------------------------------
Total: 100 operations    = ฿0.83
```

**Revenue:** ฿890
**Cost:** ฿50.83 (infra + AI)
**Profit:** ฿839.17 (94.3%)

✅ **Perfect fit for Starter package**

---

### **Scenario 2: Active Manager (Pro)**

**Profile:**
- Facility manager
- Uses AI daily for quick insights
- Snaps photos of waste regularly

**Typical Usage (per month):**
```
500 general questions    = ฿3.50
100 summary reports      = ฿1.10
50 transaction queries   = ฿0.60
30 transaction inserts   = ฿0.30
200 images (snap & sort) = ฿4.80
80 charts                = ฿0.88
30 alert checks          = ฿0.33
10 GRI reports           = ฿0.13
--------------------------------
Total: 1,000 operations  = ฿11.64
```

**Revenue:** ฿3,500
**Cost:** ฿161.64 (infra + AI)
**Profit:** ฿3,338.36 (95.4%)

✅ **Well within Pro package limits (2,000 ops)**
💡 **User has 1,000 operations remaining for growth**

---

### **Scenario 3: Enterprise Factory (Enterprise)**

**Profile:**
- Large manufacturing facility
- Multiple managers using system
- Heavy reporting requirements

**Typical Usage (per month):**
```
2,000 general questions  = ฿14.00
500 summary reports      = ฿5.50
200 transaction queries  = ฿2.40
150 transaction inserts  = ฿1.50
1,000 images             = ฿24.00
300 charts               = ฿3.30
100 alert checks         = ฿1.10
50 GRI reports           = ฿0.65
--------------------------------
Total: 4,300 operations  = ฿52.45
```

**Revenue:** ฿12,000
**Cost:** ฿552.45 (infra + AI)
**Profit:** ฿11,447.55 (95.4%)

✅ **Unlimited plan is highly profitable even at 4,300+ ops**
💡 **Can support 10,000+ operations and still maintain >90% margin**

---

## 🚨 Cost Alerts & Limits

### **When to Upgrade Users:**

```python
UPGRADE_THRESHOLDS = {
    "starter": {
        "warning_at": 80,      # 80 operations (80% of limit)
        "block_at": 100,       # Hard limit
        "suggest_upgrade": "pro"
    },
    "pro": {
        "warning_at": 1600,    # 1,600 operations (80% of limit)
        "block_at": 2000,      # Hard limit
        "suggest_upgrade": "enterprise"
    },
    "enterprise": {
        "warning_at": None,    # No warnings
        "block_at": None,      # Unlimited
        "fair_use_policy": 50000  # Extreme usage review
    }
}
```

### **Implementation:**

```python
async def check_usage_limit(user_id: str, package: str):
    """
    Check if user is approaching their usage limit
    """
    current_usage = await get_monthly_operations(user_id)
    limits = UPGRADE_THRESHOLDS[package]

    if limits["block_at"] and current_usage >= limits["block_at"]:
        return {
            "status": "blocked",
            "message": "Monthly limit reached. Please upgrade to continue.",
            "upgrade_to": limits["suggest_upgrade"]
        }

    if limits["warning_at"] and current_usage >= limits["warning_at"]:
        remaining = limits["block_at"] - current_usage
        return {
            "status": "warning",
            "message": f"You have {remaining} operations remaining this month.",
            "usage_percentage": (current_usage / limits["block_at"]) * 100
        }

    return {
        "status": "ok",
        "current_usage": current_usage,
        "limit": limits["block_at"]
    }
```

---

## 💡 Optimization Tips

### **1. Encourage Batch Operations**

Instead of:
- User asks "What's my waste today?" → 1 operation
- User asks "What's my waste yesterday?" → 1 operation
- User asks "What's my waste this week?" → 1 operation

**Total:** 3 operations (฿0.033)

Encourage:
- User asks "Show me my waste for the last 7 days" → 1 operation

**Total:** 1 operation (฿0.011)
**Savings:** 67%

---

### **2. Use Scheduled Reports (Free!)**

Instead of users manually requesting daily summaries:

```python
# Run at 6 AM daily (batch mode)
@scheduler.scheduled_job('cron', hour=6)
async def send_daily_summaries():
    """
    Generate and push daily summaries via LINE Notify
    No AI cost (pre-generated), just notification cost
    """
    users = await get_active_pro_users()

    for user in users:
        summary = await generate_summary(user.id)  # Python only
        await line_notify.send(user.line_id, summary)

    # Cost: $0 (no Gemini calls, just data aggregation)
```

**User Experience:** Better (automatic notifications)
**Cost:** FREE (Python data aggregation only)
**Win-win!**

---

### **3. Image Pre-processing**

Before sending images to Gemini:

```python
def optimize_image(image_bytes: bytes) -> bytes:
    """
    Reduce image token cost by 50%
    """
    img = Image.open(BytesIO(image_bytes))

    # Resize to max 1024x1024
    img.thumbnail((1024, 1024), Image.LANCZOS)

    # Compress to 80% quality
    output = BytesIO()
    img.save(output, format='JPEG', quality=80, optimize=True)

    return output.getvalue()

# Cost reduction:
# Before: 1,500 tokens → ฿0.024
# After: 800 tokens → ฿0.013
# Savings: 46%
```

---

## 📊 Monthly P&L Template

```
GEPP LINE AI Manager - Monthly P&L

Package: Pro
Subscribers: 100 users

REVENUE:
  100 users × ฿3,500        = ฿350,000

COSTS:
  AI Cost (per user):
    - 1,500 text ops         = ฿16.50
    - 500 image ops          = ฿12.00
    - Subtotal               = ฿28.50
  AI Cost (total)            = ฿2,850

  Infrastructure:
    - Base cost (100 users)  = ฿15,000
    - Operations overhead    = ฿5,000
    - Subtotal               = ฿20,000

  Total Monthly Costs        = ฿22,850

PROFIT:
  Gross Profit               = ฿327,150
  Profit Margin              = 93.5%

UNIT ECONOMICS:
  Revenue per user           = ฿3,500
  Cost per user              = ฿228.50
  Profit per user            = ฿3,271.50
  LTV (12 months)            = ฿39,258
```

✅ **Highly profitable SaaS model**

---

## 🎯 Recommended Package Strategy

| Package | Price | Limit | Image Limit | Target User | Margin |
|---------|-------|-------|-------------|-------------|--------|
| **Starter** | ฿890 | 100 ops | 0 | Small Business | 94% |
| **Pro** | ฿3,500 | 2,000 ops | 500 | Facility Manager | 95% |
| **Enterprise** | ฿12,000 | Unlimited | Unlimited | Large Factory | 94% |

**Upsell Path:**
```
Starter → Pro (when > 80 ops/month)
Pro → Enterprise (when > 1,600 ops/month OR needs advanced features)
```

---

## 📞 Support

For questions about pricing strategy or cost calculations:
- Email: [your-email]
- LINE: @gepp-support

---

**Document Version:** 1.0
**Last Updated:** February 10, 2026
**Author:** GEPP Sa-Ard Business Team
