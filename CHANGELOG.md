# Changelog

## [Unreleased]

### Added
- **Local Development Environment**: Complete LocalStack-based setup for isolated local testing
  - Docker Compose configuration for LocalStack services
  - Local API server that simulates Lambda execution
  - Environment-based configuration switching
  - Safety verification script to ensure production isolation
  - Comprehensive documentation in LOCAL_DEVELOPMENT.md

- **Classification API Enhancement**: Added support for confidence arrays (Issue #4)
  - New optional fields: `family_confidence_array`, `genus_confidence_array`, `species_confidence_array`
  - These fields accept arrays of numbers representing probability distributions
  - Backward compatible - existing clients continue to work without modification
  - Arrays are stored as JSON in DynamoDB with proper Decimal conversion

### Changed
- Updated API schema to include confidence array definitions
- Updated DB schema to support storing array fields
- Enhanced Lambda handler to process and store confidence arrays
- Added configuration module for environment-specific settings

### Security
- Implemented complete isolation between local and production environments
- Added safety checks to prevent accidental production access from local setup
- Environment variables clearly distinguish between local and production modes