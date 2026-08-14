-- ============================================================================
-- Migration: what a destination DOES with the material it receives
-- Date: 2026-08-13
-- Description: A traceability leg only counts as finished when it carries a
--              disposal_method — that is the field the board reads to move a
--              card into "ปลายทาง (จัดการสำเร็จ)", and the field the recycling
--              rate reads to classify the weight as recycled or disposed.
--
--              A scale can say WHERE material went. It cannot say what happened
--              to it there, and the tablet is a separate app we do not change.
--              So legs created from a weigh-out arrived with no method, sat in
--              "รอดำเนินการขนส่งต่อ" forever, and their weight fell back to being
--              guessed from the material category — which is exactly what
--              tracing was supposed to replace.
--
--              The answer does not change per shipment: a scrap dealer recycles
--              every load, a landfill landfills every load. So it belongs on the
--              destination, set once, rather than being asked on every trip.
--
--              NULL means "this destination is a waypoint, not an ending" — a
--              sorting centre that ships onward. That is the value on every
--              existing row, so nothing changes until an admin fills it in.
--
--              Values are the GRI 306-1 methods the web form already offers
--              ('Recycle', 'Municipality receive', …). Deliberately not
--              constrained here: the list lives in application code and a CHECK
--              would have to be migrated in lockstep with it.
-- ============================================================================

ALTER TABLE user_locations
    ADD COLUMN IF NOT EXISTS default_disposal_method VARCHAR(100) NULL;

COMMENT ON COLUMN user_locations.default_disposal_method IS
    'GRI 306-1 method applied to material arriving here, which also marks the leg as final. NULL = a waypoint that ships onward. See migration 084.';
