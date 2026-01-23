-- Migration: Transaction System
-- Date: 2025-01-09 12:20:00
-- Description: Creates comprehensive transaction and waste management tables

-- Main Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    
    -- Basic transaction info
    transaction_number VARCHAR(100) UNIQUE,
    transaction_type VARCHAR(50), -- 'collection', 'processing', 'disposal', 'transfer'
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'confirmed', 'processing', 'completed', 'cancelled'
    
    -- Organizations involved
    from_organization_id BIGINT REFERENCES organizations(id),
    to_organization_id BIGINT REFERENCES organizations(id),
    
    -- User locations involved
    from_location_id BIGINT REFERENCES user_locations(id),
    to_location_id BIGINT REFERENCES user_locations(id),
    
    -- Transaction details
    waste_type VARCHAR(100),
    material_id BIGINT REFERENCES materials(id),
    quantity DECIMAL(10, 3),
    unit VARCHAR(20),
    weight_kg DECIMAL(10, 3),
    
    -- Financial
    price_per_unit DECIMAL(12, 2),
    total_amount DECIMAL(12, 2),
    currency_id BIGINT REFERENCES currencies(id) DEFAULT 12,
    
    -- Dates
    transaction_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    scheduled_date TIMESTAMP WITH TIME ZONE,
    completed_date TIMESTAMP WITH TIME ZONE,
    
    -- Location and logistics
    pickup_address TEXT,
    delivery_address TEXT,
    pickup_coordinate TEXT, -- "lat,lng"
    delivery_coordinate TEXT, -- "lat,lng"
    
    -- Documentation
    notes TEXT,
    special_instructions TEXT,
    images JSONB, -- Array of image URLs
    documents JSONB, -- Array of document URLs
    
    -- Tracking
    tracking_number VARCHAR(100),
    vehicle_info JSONB,
    driver_info JSONB,
    
    -- Compliance and reporting
    waste_code VARCHAR(50),
    hazardous_level VARCHAR(20), -- 'non-hazardous', 'low', 'medium', 'high'
    treatment_method VARCHAR(100),
    disposal_method VARCHAR(100),
    
    -- System fields
    created_by_id BIGINT REFERENCES user_locations(id),
    updated_by_id BIGINT REFERENCES user_locations(id),
    approved_by_id BIGINT REFERENCES user_locations(id),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Transaction Items (for multiple items in one transaction)
CREATE TABLE IF NOT EXISTS transaction_items (
    id BIGSERIAL PRIMARY KEY,
    transaction_id BIGINT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    
    material_id BIGINT REFERENCES materials(id),
    waste_type VARCHAR(100),
    description TEXT,
    
    quantity DECIMAL(10, 3),
    unit VARCHAR(20),
    weight_kg DECIMAL(10, 3),
    
    price_per_unit DECIMAL(12, 2),
    total_amount DECIMAL(12, 2),
    
    -- Item-specific details
    condition_rating INTEGER, -- 1-10 scale
    contamination_level VARCHAR(20),
    processing_notes TEXT,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Transaction Status History
CREATE TABLE IF NOT EXISTS transaction_status_history (
    id BIGSERIAL PRIMARY KEY,
    transaction_id BIGINT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    
    status VARCHAR(50),
    previous_status VARCHAR(50),
    reason TEXT,
    notes TEXT,
    
    changed_by_id BIGINT REFERENCES user_locations(id),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Waste Collections (for tracking collection events)
CREATE TABLE IF NOT EXISTS waste_collections (
    id BIGSERIAL PRIMARY KEY,
    transaction_id BIGINT REFERENCES transactions(id),
    
    collection_date TIMESTAMP WITH TIME ZONE,
    collection_address TEXT,
    collection_coordinate TEXT, -- "lat,lng"
    
    collector_id BIGINT REFERENCES user_locations(id),
    collection_team JSONB, -- Array of team member info
    
    vehicle_type VARCHAR(50),
    vehicle_plate VARCHAR(20),
    vehicle_capacity DECIMAL(10, 3),
    
    collection_method VARCHAR(50), -- 'manual', 'automated', 'mixed'
    container_types JSONB, -- Array of container info
    
    weather_conditions VARCHAR(50),
    traffic_conditions VARCHAR(50),
    
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    
    notes TEXT,
    images JSONB,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Waste Processing (for tracking processing activities)
CREATE TABLE IF NOT EXISTS waste_processing (
    id BIGSERIAL PRIMARY KEY,
    transaction_id BIGINT REFERENCES transactions(id),
    
    processing_date TIMESTAMP WITH TIME ZONE,
    processing_facility_id BIGINT REFERENCES user_locations(id),
    
    input_weight DECIMAL(10, 3),
    output_weight DECIMAL(10, 3),
    waste_reduction_percent DECIMAL(5, 2),
    
    processing_method VARCHAR(100),
    processing_equipment JSONB,
    processing_duration INTEGER, -- minutes
    
    quality_grade VARCHAR(20),
    contamination_removed DECIMAL(10, 3),
    
    byproducts JSONB, -- Array of byproduct info
    residue_amount DECIMAL(10, 3),
    residue_disposal_method VARCHAR(100),
    
    energy_consumed DECIMAL(10, 3), -- kWh
    water_used DECIMAL(10, 3), -- liters
    
    operator_id BIGINT REFERENCES user_locations(id),
    supervisor_id BIGINT REFERENCES user_locations(id),
    
    notes TEXT,
    processing_report_url TEXT,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Transaction Payments
CREATE TABLE IF NOT EXISTS transaction_payments (
    id BIGSERIAL PRIMARY KEY,
    transaction_id BIGINT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    
    payment_method VARCHAR(50), -- 'cash', 'bank_transfer', 'credit_card', 'digital_wallet'
    payment_status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'paid', 'partial', 'refunded', 'cancelled'
    
    amount DECIMAL(12, 2),
    currency_id BIGINT REFERENCES currencies(id) DEFAULT 12,
    
    payment_date TIMESTAMP WITH TIME ZONE,
    due_date TIMESTAMP WITH TIME ZONE,
    
    payer_id BIGINT REFERENCES user_locations(id),
    payee_id BIGINT REFERENCES user_locations(id),
    
    payment_reference VARCHAR(100),
    bank_reference VARCHAR(100),
    
    -- Payment gateway info
    gateway_transaction_id VARCHAR(255),
    gateway_response JSONB,
    
    notes TEXT,
    receipt_url TEXT,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Transaction Analytics (for reporting and insights)
CREATE TABLE IF NOT EXISTS transaction_analytics (
    id BIGSERIAL PRIMARY KEY,
    transaction_id BIGINT REFERENCES transactions(id) ON DELETE CASCADE,
    
    -- Performance metrics
    processing_efficiency DECIMAL(5, 2), -- percentage
    cost_per_kg DECIMAL(10, 4),
    environmental_impact_score INTEGER,
    
    -- Time metrics
    collection_duration INTEGER, -- minutes
    processing_duration INTEGER, -- minutes
    total_cycle_time INTEGER, -- minutes
    
    -- Quality metrics
    contamination_rate DECIMAL(5, 2), -- percentage
    recovery_rate DECIMAL(5, 2), -- percentage
    quality_score INTEGER, -- 1-100
    
    -- Financial metrics
    revenue DECIMAL(12, 2),
    costs DECIMAL(12, 2),
    profit_margin DECIMAL(5, 2), -- percentage
    
    -- Environmental metrics
    carbon_footprint DECIMAL(10, 3), -- kg CO2
    energy_efficiency DECIMAL(10, 3), -- kWh per kg
    water_usage DECIMAL(10, 3), -- liters per kg
    
    calculated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Supporting Documents
CREATE TABLE IF NOT EXISTS transaction_documents (
    id BIGSERIAL PRIMARY KEY,
    transaction_id BIGINT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    
    document_type VARCHAR(50), -- 'manifest', 'certificate', 'invoice', 'receipt', 'permit'
    document_name VARCHAR(255),
    file_url TEXT,
    file_size INTEGER, -- bytes
    file_type VARCHAR(50), -- 'pdf', 'jpg', 'png', etc.
    
    uploaded_by_id BIGINT REFERENCES user_locations(id),
    verified_by_id BIGINT REFERENCES user_locations(id),
    verification_status VARCHAR(50) DEFAULT 'pending',
    verification_date TIMESTAMP WITH TIME ZONE,
    
    expiry_date TIMESTAMP WITH TIME ZONE,
    is_required BOOLEAN DEFAULT FALSE,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_transactions_number ON transactions(transaction_number);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_from_org ON transactions(from_organization_id);
CREATE INDEX IF NOT EXISTS idx_transactions_to_org ON transactions(to_organization_id);
CREATE INDEX IF NOT EXISTS idx_transactions_from_location ON transactions(from_location_id);
CREATE INDEX IF NOT EXISTS idx_transactions_to_location ON transactions(to_location_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_material ON transactions(material_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created_by ON transactions(created_by_id);

CREATE INDEX IF NOT EXISTS idx_transaction_items_transaction ON transaction_items(transaction_id);
CREATE INDEX IF NOT EXISTS idx_transaction_items_material ON transaction_items(material_id);

CREATE INDEX IF NOT EXISTS idx_transaction_status_history_transaction ON transaction_status_history(transaction_id);
CREATE INDEX IF NOT EXISTS idx_transaction_status_history_status ON transaction_status_history(status);
CREATE INDEX IF NOT EXISTS idx_transaction_status_history_date ON transaction_status_history(changed_at);

CREATE INDEX IF NOT EXISTS idx_waste_collections_transaction ON waste_collections(transaction_id);
CREATE INDEX IF NOT EXISTS idx_waste_collections_date ON waste_collections(collection_date);
CREATE INDEX IF NOT EXISTS idx_waste_collections_collector ON waste_collections(collector_id);

CREATE INDEX IF NOT EXISTS idx_waste_processing_transaction ON waste_processing(transaction_id);
CREATE INDEX IF NOT EXISTS idx_waste_processing_facility ON waste_processing(processing_facility_id);
CREATE INDEX IF NOT EXISTS idx_waste_processing_date ON waste_processing(processing_date);

CREATE INDEX IF NOT EXISTS idx_transaction_payments_transaction ON transaction_payments(transaction_id);
CREATE INDEX IF NOT EXISTS idx_transaction_payments_status ON transaction_payments(payment_status);
CREATE INDEX IF NOT EXISTS idx_transaction_payments_date ON transaction_payments(payment_date);

-- Create triggers for updated_date columns
CREATE TRIGGER update_transactions_updated_date BEFORE UPDATE ON transactions
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_transaction_items_updated_date BEFORE UPDATE ON transaction_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_waste_collections_updated_date BEFORE UPDATE ON waste_collections
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_waste_processing_updated_date BEFORE UPDATE ON waste_processing
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_transaction_payments_updated_date BEFORE UPDATE ON transaction_payments
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_transaction_documents_updated_date BEFORE UPDATE ON transaction_documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();