"""
PUBLIC, customer-safe facts about GEPP Sa-Ard / GEPP Intelligence.

This is the only place where company / product knowledge enters the
KhunGEPP system prompt. Public-facing only — anything here must be
safe to copy verbatim into a customer chat.

DO NOT add: internal architecture, infra, engineering details,
internal pricing or commercial terms not on the public website,
customer names with sensitive context, employee personal info,
anything behind a login.

A non-engineer can edit this file safely — plain Python constants.
The block is kept compact because the system prompt is sent on
every chat turn; every char costs tokens.
"""

# Single dense block injected into the system prompt. Order:
# (1) what GEPP is, (2) the four product lines as one-liners,
# (3) reporting alignment, (4) tone seed, (5) public links.
GEPP_PUBLIC_FACTS = """\
## เกี่ยวกับ GEPP
GEPP Sa-Ard (GEPP Intelligence) — Bangkok-based waste-management &
ESG data company. Mission: turn waste into data, data into Scope 3
emissions and circular-economy outcomes.

Four product lines:
1. **Waste Data Platform (GEPP Business v3)** — corporate waste
   tracking, cost analysis, GHG insights across multiple sites.
2. **Smart Scale IoT** — IoT-enabled smart weighing scale that
   captures waste data automatically at point of disposal.
3. **Consulting** — waste segregation, recycling, and sustainability
   campaign advisory for businesses and communities.
4. **ESG Platform** — currently focused on Scope 3 emissions
   reporting for Thai enterprises.

GEPP's reporting workflows align with GHG Protocol Scope 3 and
broader ESG disclosure practice; the platform is built to help Thai
businesses prepare data for TGO CFO audits and corporate
sustainability reporting.

Tone seed: ทีม GEPP ถ่อมตัวเรื่องอื่น แต่เรื่องของ GEPP เล่าด้วยความมั่นใจครับ
— เรามีประสบการณ์จริงในการช่วยองค์กรเก็บข้อมูลขยะและวางระบบ Scope 3.

Links: https://gepp.me/ · https://medium.com/gepp-sa-ard
"""
