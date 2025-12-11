# GRI Module - Global Reporting Initiative Waste Management Standards

## Overview

This module implements support for GRI 306 Waste standards, enabling organizations to track and report their waste management performance.

## Data Models

### GRI 306-1: Waste Generation and Significant Waste-Related Impacts
Table: `gri306_1`
- Records waste generation events
- Tracks input materials, activities, and outputs
- Links to materials and categories

### GRI 306-2: Management of Significant Waste-Related Impacts
Table: `gri306_2`
- Tracks management approaches for waste
- Links to GRI 306-1 records (`approached_id`)
- prevention actions, verification methods

### GRI 306-3: Waste Generated
Table: `gri306_3`
- Records spills and leaks details
- Volume, location, cleanup costs

### GRI 306 Export
Table: `gri306_export`
- History of generated reports/exports
