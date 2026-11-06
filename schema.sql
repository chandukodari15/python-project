-- ============================================================================
-- WATTWISE: Electricity Consumption Analysis System
-- Production MySQL Schema Definition
-- Version: 2.0.0
-- ============================================================================

CREATE DATABASE IF NOT EXISTS electricity_analysis
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE electricity_analysis;

-- ----------------------------------------------------------------------------
-- Table: consumers
-- Stores individual households, commercial facilities, and industrial clients
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consumers (
  consumer_id INT AUTO_INCREMENT PRIMARY KEY,
  consumer_name VARCHAR(100) NOT NULL,
  consumer_type ENUM('Residential','Commercial','Industrial','Agricultural','Other') NOT NULL DEFAULT 'Residential',
  region VARCHAR(100) NOT NULL,
  phone VARCHAR(25) NULL,
  email VARCHAR(120) NULL,
  status ENUM('Active','Inactive') NOT NULL DEFAULT 'Active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_consumers_region(region),
  INDEX idx_consumers_status(status),
  INDEX idx_consumers_type(consumer_type)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- Table: meters
-- Physical electricity metering devices linked to consumers
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meters (
  meter_id INT AUTO_INCREMENT PRIMARY KEY,
  consumer_id INT NOT NULL,
  meter_code VARCHAR(50) NOT NULL UNIQUE,
  meter_capacity DECIMAL(12,2) NULL,
  status ENUM('Active','Inactive') NOT NULL DEFAULT 'Active',
  installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_meters_consumer FOREIGN KEY (consumer_id)
    REFERENCES consumers(consumer_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  INDEX idx_meters_consumer(consumer_id),
  INDEX idx_meters_status(status)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- Table: meter_readings
-- Time-series cumulative meter readings and calculated consumption
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meter_readings (
  reading_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  meter_id INT NOT NULL,
  reading_date DATE NOT NULL,
  cumulative_kwh DECIMAL(12,2) NOT NULL,
  consumption_kwh DECIMAL(12,2) NULL,
  notes VARCHAR(500) NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_readings_meter FOREIGN KEY (meter_id)
    REFERENCES meters(meter_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_cumulative_kwh CHECK (cumulative_kwh >= 0),
  UNIQUE KEY uq_meter_reading_date(meter_id, reading_date),
  INDEX idx_readings_date(reading_date),
  INDEX idx_readings_meter_date(meter_id, reading_date)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- Table: system_settings
-- System-level analytical configurations, thresholds, and tariff preferences
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_settings (
  setting_key VARCHAR(50) PRIMARY KEY,
  setting_value VARCHAR(255) NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

INSERT INTO system_settings (setting_key, setting_value)
VALUES ('high_usage_threshold', '500')
ON DUPLICATE KEY UPDATE setting_value = setting_value;

-- ----------------------------------------------------------------------------
-- Triggers: Automatic consumption calculation on Insert and Update
-- ----------------------------------------------------------------------------
DELIMITER //

DROP TRIGGER IF EXISTS before_meter_reading_insert //
CREATE TRIGGER before_meter_reading_insert
BEFORE INSERT ON meter_readings
FOR EACH ROW
BEGIN
  DECLARE previous_value DECIMAL(12,2);
  SELECT cumulative_kwh INTO previous_value
  FROM meter_readings
  WHERE meter_id = NEW.meter_id AND reading_date < NEW.reading_date
  ORDER BY reading_date DESC, reading_id DESC LIMIT 1;

  IF previous_value IS NOT NULL AND NEW.cumulative_kwh < previous_value THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cumulative reading cannot be lower than the previous reading; verify meter reset/rollover.';
  END IF;

  IF previous_value IS NOT NULL THEN
    SET NEW.consumption_kwh = NEW.cumulative_kwh - previous_value;
  ELSE
    SET NEW.consumption_kwh = NULL;
  END IF;
END //

DROP TRIGGER IF EXISTS before_meter_reading_update //
CREATE TRIGGER before_meter_reading_update
BEFORE UPDATE ON meter_readings
FOR EACH ROW
BEGIN
  DECLARE previous_value DECIMAL(12,2);
  SELECT cumulative_kwh INTO previous_value
  FROM meter_readings
  WHERE meter_id = NEW.meter_id AND reading_date < NEW.reading_date
    AND reading_id <> OLD.reading_id
  ORDER BY reading_date DESC, reading_id DESC LIMIT 1;

  IF previous_value IS NOT NULL AND NEW.cumulative_kwh < previous_value THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cumulative reading cannot be lower than the previous reading.';
  END IF;

  IF previous_value IS NOT NULL THEN
    SET NEW.consumption_kwh = NEW.cumulative_kwh - previous_value;
  ELSE
    SET NEW.consumption_kwh = NULL;
  END IF;
END //

DELIMITER ;
