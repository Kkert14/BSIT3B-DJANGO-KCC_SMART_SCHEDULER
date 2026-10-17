-- =====================================================================
-- SMART SCHEDULER: database schema (v4, 7 tables)
-- Tables: buildings, rooms, programs, teachers, sections, subjects, schedules
-- Target: MySQL 8.0.16+ / MariaDB 10.4+ (InnoDB, utf8mb4)
--
-- How to use
--  1. Import through phpMyAdmin (Import tab) or: mysql -u root -p < smart_scheduler_v4.sql
--  2. The LAST statement links teachers to Django's auth_user table. If it fails
--     because auth_user does not exist yet, run `python manage.py migrate` and then
--     run only that last ALTER TABLE statement again. Everything else is unaffected.
--
-- Conventions
--  * academic_year is text in the form 'YYYY-YYYY' (for example '2026-2027').
--  * semester is a number: 1 = First, 2 = Second, 3 = Summer.
--  * day_of_week is a number: 1 = Monday ... 7 = Sunday.
--  * class_type is 'Lecture' or 'Laboratory'.
--  * Overlapping times and the per-subject time limit are checked in Django,
--    not here. The database blocks identical start times and keeps lookups fast.
--  * Admin and teacher roles use Django Groups (created by Django, not by this file).
-- =====================================================================

CREATE DATABASE IF NOT EXISTS `smart_scheduler`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE `smart_scheduler`;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `schedules`;
DROP TABLE IF EXISTS `subjects`;
DROP TABLE IF EXISTS `sections`;
DROP TABLE IF EXISTS `teachers`;
DROP TABLE IF EXISTS `programs`;
DROP TABLE IF EXISTS `rooms`;
DROP TABLE IF EXISTS `buildings`;

SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
-- 1. Buildings and rooms
-- ---------------------------------------------------------------------

CREATE TABLE `buildings` (
  `id`        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `code`      VARCHAR(20) NOT NULL,
  `name`      VARCHAR(100) NOT NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_buildings_code` (`code`),
  UNIQUE KEY `uq_buildings_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `rooms` (
  `id`          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `building_id` BIGINT UNSIGNED NOT NULL,
  `room_name`   VARCHAR(120) NOT NULL,
  `room_type`   VARCHAR(30) NOT NULL DEFAULT 'Classroom',
  `capacity`    SMALLINT UNSIGNED NOT NULL,
  `is_active`   TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  -- Two buildings may both have a "ROOM 101", but not twice in the same building.
  UNIQUE KEY `uq_rooms_building_name` (`building_id`, `room_name`),
  CONSTRAINT `fk_rooms_building` FOREIGN KEY (`building_id`)
    REFERENCES `buildings` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_rooms_type` CHECK (`room_type` IN ('Classroom', 'Laboratory', 'Lecture Hall', 'Other'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 2. Programs, teachers, sections
-- ---------------------------------------------------------------------

CREATE TABLE `programs` (
  `id`        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `code`      VARCHAR(20) NOT NULL,
  `name`      VARCHAR(150) NOT NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_programs_code` (`code`),
  UNIQUE KEY `uq_programs_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `teachers` (
  `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_id`         INT NULL COMMENT 'Login account (auth_user.id). NULL = teacher has no login.',
  `employee_number` VARCHAR(30) NOT NULL,
  `first_name`      VARCHAR(100) NOT NULL,
  `last_name`       VARCHAR(100) NOT NULL,
  `contact_number`  VARCHAR(30) NOT NULL DEFAULT '',
  `is_active`       TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_teachers_user` (`user_id`),
  UNIQUE KEY `uq_teachers_employee_number` (`employee_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `sections` (
  `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name`          VARCHAR(50) NOT NULL,
  `program_id`    BIGINT UNSIGNED NOT NULL,
  `year_level`    SMALLINT UNSIGNED NOT NULL,
  `academic_year` VARCHAR(9) NOT NULL,
  `capacity`      SMALLINT UNSIGNED NOT NULL,
  `is_active`     TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sections_identity` (`academic_year`, `program_id`, `year_level`, `name`),
  KEY `ix_sections_program` (`program_id`),
  CONSTRAINT `fk_sections_program` FOREIGN KEY (`program_id`)
    REFERENCES `programs` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_sections_year_level` CHECK (`year_level` BETWEEN 1 AND 6),
  CONSTRAINT `ck_sections_academic_year` CHECK (`academic_year` REGEXP '^[0-9]{4}-[0-9]{4}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 3. Subjects (the curriculum lives here)
--    One row = one subject in one program, academic year, year level and semester.
--    The same subject in a different academic year or semester is a different row.
-- ---------------------------------------------------------------------

CREATE TABLE `subjects` (
  `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `code`            VARCHAR(20) NOT NULL,
  `name`            VARCHAR(150) NOT NULL,
  `units`           DECIMAL(3,1) NOT NULL,
  `lec_hours`       SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Lecture hours per week',
  `lab_hours`       SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Laboratory hours per week',
  `program_id`      BIGINT UNSIGNED NOT NULL,
  `academic_year`   VARCHAR(9) NOT NULL,
  `year_level`      SMALLINT UNSIGNED NOT NULL,
  `semester`        SMALLINT UNSIGNED NOT NULL COMMENT '1 = First, 2 = Second, 3 = Summer',
  `prerequisite_id` BIGINT UNSIGNED NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_subjects_identity` (`program_id`, `code`, `academic_year`, `semester`),
  KEY `ix_subjects_curriculum` (`program_id`, `academic_year`, `year_level`, `semester`),
  KEY `ix_subjects_prerequisite` (`prerequisite_id`),
  CONSTRAINT `fk_subjects_program` FOREIGN KEY (`program_id`)
    REFERENCES `programs` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_subjects_prerequisite` FOREIGN KEY (`prerequisite_id`)
    REFERENCES `subjects` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_subjects_academic_year` CHECK (`academic_year` REGEXP '^[0-9]{4}-[0-9]{4}$'),
  CONSTRAINT `ck_subjects_year_level` CHECK (`year_level` BETWEEN 1 AND 6),
  CONSTRAINT `ck_subjects_semester` CHECK (`semester` BETWEEN 1 AND 3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 4. Schedules
--    academic_year and semester are required on every row (NOT NULL, no default).
--    Time limit per subject (checked in Django): for one section, subject,
--    academic year and semester, the total Lecture time cannot exceed
--    subjects.lec_hours and the total Laboratory time cannot exceed
--    subjects.lab_hours.
-- ---------------------------------------------------------------------

CREATE TABLE `schedules` (
  `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `academic_year` VARCHAR(9) NOT NULL,
  `semester`      SMALLINT UNSIGNED NOT NULL COMMENT '1 = First, 2 = Second, 3 = Summer',
  `teacher_id`    BIGINT UNSIGNED NOT NULL,
  `subject_id`    BIGINT UNSIGNED NOT NULL,
  `section_id`    BIGINT UNSIGNED NOT NULL,
  `room_id`       BIGINT UNSIGNED NOT NULL,
  `class_type`    VARCHAR(12) NOT NULL COMMENT 'Lecture or Laboratory',
  `day_of_week`   SMALLINT UNSIGNED NOT NULL COMMENT '1 = Monday ... 7 = Sunday',
  `start_time`    TIME NOT NULL,
  `end_time`      TIME NOT NULL,
  `created_at`    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at`    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  -- Identical start times are blocked here. Partial overlaps are checked in Django.
  UNIQUE KEY `uq_schedule_teacher_start` (`teacher_id`, `academic_year`, `semester`, `day_of_week`, `start_time`),
  UNIQUE KEY `uq_schedule_room_start`    (`room_id`,    `academic_year`, `semester`, `day_of_week`, `start_time`),
  UNIQUE KEY `uq_schedule_section_start` (`section_id`, `academic_year`, `semester`, `day_of_week`, `start_time`),
  KEY `ix_schedules_term` (`academic_year`, `semester`),
  KEY `ix_schedules_subject_section` (`subject_id`, `section_id`),
  CONSTRAINT `fk_schedules_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `teachers` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_schedules_subject` FOREIGN KEY (`subject_id`) REFERENCES `subjects` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_schedules_section` FOREIGN KEY (`section_id`) REFERENCES `sections` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_schedules_room`    FOREIGN KEY (`room_id`)    REFERENCES `rooms` (`id`)    ON DELETE RESTRICT,
  CONSTRAINT `ck_schedules_academic_year` CHECK (`academic_year` REGEXP '^[0-9]{4}-[0-9]{4}$'),
  CONSTRAINT `ck_schedules_semester` CHECK (`semester` BETWEEN 1 AND 3),
  CONSTRAINT `ck_schedules_class_type` CHECK (`class_type` IN ('Lecture', 'Laboratory')),
  CONSTRAINT `ck_schedules_day` CHECK (`day_of_week` BETWEEN 1 AND 7),
  CONSTRAINT `ck_schedules_times` CHECK (`end_time` > `start_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- Seed data (from the teacher's scheddb.sql: buildings, course, subject)
-- =====================================================================

INSERT INTO `buildings` (`code`, `name`) VALUES
  ('COLLEGE', 'College Building'),
  ('CMAT',    'CMAT Building');

INSERT INTO `programs` (`code`, `name`) VALUES
  ('BSA',  'Bachelor of Science in Accountancy'),
  ('BSMA', 'Bachelor of Science in Management Accounting');

INSERT INTO `subjects`
  (`code`, `name`, `units`, `lec_hours`, `lab_hours`, `program_id`, `academic_year`, `year_level`, `semester`)
SELECT v.code, v.name, v.units, v.lec, v.lab, p.id, v.ay, v.yr, v.sem
FROM (
  SELECT 'BSMA101' AS code, 'Mathematics Orientation' AS name, 3.0 AS units, 3 AS lec, 0 AS lab,
         'BSMA' AS pcode, '2024-2025' AS ay, 1 AS yr, 1 AS sem
  UNION ALL SELECT 'BSMA102', 'Calculus I',                          3.0, 3, 3, 'BSMA', '2024-2025', 1, 1
  UNION ALL SELECT 'BSA101',  'Accounting Basics',                   3.0, 3, 0, 'BSA',  '2024-2025', 1, 1
  UNION ALL SELECT 'ITE 107', 'Web Applications and Technologies 2', 2.0, 2, 3, 'BSMA', '2026-2027', 1, 1
  UNION ALL SELECT 'ITE 301', 'Networking 1',                        2.0, 2, 3, 'BSMA', '2026-2027', 1, 2
  UNION ALL SELECT 'ITE 302', 'Networking 2',                        2.0, 2, 3, 'BSMA', '2026-2027', 2, 1
) v
JOIN `programs` p ON p.code = v.pcode;

-- Prerequisite: Networking 2 requires Networking 1 (same program and academic year).
UPDATE `subjects` s2
JOIN `subjects` s1
  ON s1.program_id = s2.program_id
 AND s1.academic_year = s2.academic_year
 AND s1.code = 'ITE 301'
SET s2.prerequisite_id = s1.id
WHERE s2.code = 'ITE 302';

-- =====================================================================
-- Login link (keep this as the LAST statement)
-- Requires Django's auth_user table. If it fails, run `python manage.py migrate`
-- and then run only this statement.
-- =====================================================================

ALTER TABLE `teachers`
  ADD CONSTRAINT `fk_teachers_user` FOREIGN KEY (`user_id`)
    REFERENCES `auth_user` (`id`) ON DELETE SET NULL;
