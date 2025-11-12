# Transaction Audit Prompt Configuration

This document explains the prompt configuration structure for the Transaction Audit Service.

## Overview

The `prompt_base.json` file contains all prompt templates, system instructions, and configuration settings that were previously hardcoded in the service. This makes it easy to modify prompts without changing the code.

## File Structure

```json
{
  "system_instructions": {
    "structured_content": "System instruction for image + text analysis",
    "text_only": "System instruction for text-only analysis"
  },
  "audit_prompt": {
    "template": "Main audit prompt template with variables",
    "variables": {
      "record_count": "Description of variable",
      ...
    }
  },
  "image_analysis_instructions": {
    "template": "Additional instructions for image analysis",
    "enabled": true
  },
  "example_messages": {
    "thai": "Thai example rejection messages",
    "english": "English example rejection messages"
  },
  "language_mapping": {
    "thai": "Thai (ภาษาไทย)",
    "english": "English",
    "en": "English", 
    "th": "Thai (ภาษาไทย)"
  },
  "api_settings": {
    "model_name": "gemini-2.5-flash",
    "temperature": 0.0,
    "thinking_budget": 1024,
    "response_suffix": "Additional text appended to responses"
  },
  "metadata": {
    "version": "1.0.0",
    "description": "Base prompt structure for transaction audit service",
    "created_date": "2025-11-03",
    "last_modified": "2025-11-03"
  }
}
```

## Key Sections

### System Instructions
- `structured_content`: Used when processing both text and images
- `text_only`: Used when processing text only

### Audit Prompt Template
The main prompt template uses Python string formatting with these variables:
- `{record_count}`: Number of transaction records
- `{unique_types_count}`: Number of unique material types
- `{material_types}`: List of material types
- `{rules_json}`: JSON string of audit rules
- `{transaction_json}`: JSON string of transaction data
- `{language_name}`: Language name for prompts (Thai/English)
- `{transaction_id}`: Transaction ID

### Image Analysis Instructions
Additional instructions appended when images are present. Can be disabled by setting `"enabled": false`.

### Example Messages
Rejection message examples in different languages, used to guide the AI response format.

### Language Mapping
Maps language codes to full language names used in prompts.

### API Settings
Configuration for the Vertex AI API calls:
- `model_name`: Gemini model to use
- `temperature`: Response randomness (0.0 = deterministic)
- `thinking_budget`: Reasoning token budget
- `response_suffix`: Text appended to all responses

## Usage

The service automatically loads the configuration on initialization:

```python
service = TransactionAuditService(response_language='thai')
# Configuration loaded from prompt_base.json
```

If the JSON file is missing or invalid, the service falls back to default configuration.

## Modifying Prompts

1. Open `prompt_base.json`
2. Modify the desired section
3. Save the file
4. Restart the service to load changes

### Common Modifications

- **Changing the audit logic**: Edit the `audit_prompt.template`
- **Adding new languages**: Add entries to `language_mapping` and `example_messages`
- **Adjusting AI behavior**: Modify `system_instructions` or `api_settings.temperature`
- **Disabling image analysis**: Set `image_analysis_instructions.enabled` to false

## Variables in Templates

When editing templates, you can use these variables:
- All variables from `audit_prompt.variables`
- Any valid Python string formatting syntax
- JSON data is passed as strings using `json.dumps(data, ensure_ascii=False)`

## Fallback Behavior

If the JSON configuration fails to load:
- Basic system instructions are used
- Default language mapping (Thai/English) is applied
- Default API settings (gemini-2.5-flash, temperature 0.0) are used
- The service continues to function but with limited customization

## Version Control

- Always test changes before deploying
- Keep backups of working configurations
- Update the `metadata.version` when making significant changes
- Document changes in the `last_modified` field
