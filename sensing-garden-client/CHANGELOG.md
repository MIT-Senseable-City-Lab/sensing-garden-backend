# Changelog

All notable changes to the Sensing Garden Client will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.4] - 2025-03-23

### Changed
- Added validation for sort_desc parameter to ensure it's a boolean
- Updated API schema to properly document sort_desc as a boolean parameter
- Added test to verify sort_desc validation

## [0.0.3] - 2025-03-23

### Changed
- Removed metadata parameter from model creation method to align with API schema
- Updated client initialization to use direct constructor instead of initialize() function
- Updated example usage and documentation to reflect new API structure

## [0.0.2] - 2025-03-23

### Added
- Dedicated client classes for models, detections, and classifications (accessed via client properties)
- Comprehensive examples in README
- Shared utility functions in `shared.py` to promote code reuse
- Example script demonstrating the new API usage

### Changed
- Reverted to direct constructor initialization (`SensingGardenClient(base_url=api_base_url, api_key=api_key)`) for improved clarity and usability
- Improved type annotations throughout the codebase
- Enhanced documentation with usage examples
- Removed legacy standalone functions to simplify API structure

### Removed
- Device ID requirement from model endpoints (aligning with backend API changes)

## [0.0.1] - 2025-03-15

### Added
- Initial release of the Sensing Garden Client
- Basic client for API interactions
- GET endpoints for models, detections, and classifications
- POST endpoints for submitting detections, classifications, and models
- Basic documentation and examples
