# Snyk User Provisioning Example

This is a example Python script to provision users to Snyk organizations using the Snyk API. This script supports provisioning individual users or bulk provisioning from CSV/JSON files.

## Features

* 🔐 **Single User Provisioning**: Provision individual users to organizations
* 📋 **Bulk Provisioning**: Provision multiple users from CSV or JSON files
* 🎭 **Role Management**: Assign roles using role public IDs
* 🌍 **Multi-Region Support**: Works with all Snyk regions
* 📊 **Detailed Reporting**: Clear console output and optional JSON export
* 🔄 **Error Handling**: Robust error handling with retry logic and rate limiting

## Prerequisites

* Python 3.6 or higher
* Snyk API token with organization provisioning permissions
* Snyk organization ID
* The inviting user must have "Provision Users" permission
* SSO must be configured for the Snyk Group (if using SSO)

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Quick Start

### Provision a Single User

```bash
python provision_user_to_snyk.py \
  --token YOUR_TOKEN \
  --org-id ORG_ID \
  --email [email protected] \
  --role-public-id role-abc-123
```

### Provision Users from CSV File

```bash
python provision_user_to_snyk.py \
  --token YOUR_TOKEN \
  --org-id ORG_ID \
  --file users.csv
```

### Provision Users from JSON File

```bash
python provision_user_to_snyk.py \
  --token YOUR_TOKEN \
  --org-id ORG_ID \
  --file users.json
```

## Configuration

### Get Required Information

* **Snyk Token**: Generate from Snyk Account Settings → API Token
  * Must be a personal token (not service account token)
  * Must have "Provision Users" permission
* **Organization ID**: Found in Snyk UI or via API
* **Region**: Your Snyk region (default: SNYK-US-01)

## Usage

### Command Line Arguments

| Argument           | Required | Description                                    | Default           |
| ------------------ | -------- | ---------------------------------------------- | ----------------- |
| `--token`          | Yes*     | Snyk API token                                 | SNYK_TOKEN env var |
| `--org-id`         | Yes      | Snyk organization ID                           | -                 |
| `--email`          | Yes**    | User email address (for single user)           | -                 |
| `--file`           | Yes**    | Path to CSV or JSON file (for bulk)           | -                 |
| `--role-public-id` | Yes***   | ID of the role to grant this user             | None              |
| `--region`         | No       | Snyk region                                    | SNYK-US-01        |
| `--version`        | No       | API version                                    | 2025-11-05        |
| `--output`         | No       | Output file path for JSON results              | None              |
| `--verbose`        | No       | Include detailed DEBUG logs in log file        | False             |

\* `--token` is required if `SNYK_TOKEN` or `PERSONAL_SNYK_TOKEN` environment variable is not set.

\** Either `--email` or `--file` must be provided, but not both.

\*** `--role-public-id` is required when using `--email` for single user provisioning. Optional when using `--file` if all users in the file have `role_public_id` specified.

### Supported Regions

* `SNYK-US-01` (default) - US East
* `SNYK-US-02` - US West
* `SNYK-EU-01` - Europe
* `SNYK-AU-01` - Australia

### Role Public IDs

The script uses role public IDs to assign roles to users. You can find role public IDs in your Snyk organization settings or via the Snyk API. Role public IDs are unique identifiers for each role in your organization.

## File Formats

### CSV Format

Create a CSV file with the following columns:

```csv
email,role_public_id
[email protected],role-abc-123
[email protected],role-def-456
[email protected],role-abc-123
```

**Note**: `role_public_id` is required for each user. If you want to use a default role for users without a specified role, use the `--role-public-id` command line argument.

### JSON Format

Create a JSON file with an array of user objects:

```json
[
  {
    "email": "[email protected]",
    "role_public_id": "role-abc-123"
  },
  {
    "email": "[email protected]",
    "role_public_id": "role-def-456"
  },
  {
    "email": "[email protected]",
    "role_public_id": "role-abc-123"
  }
]
```

**Note**: `role_public_id` is required for each user. If you want to use a default role for users without a specified role, use the `--role-public-id` command line argument.

## Output

### Console Output

The script provides a formatted summary showing:
* Total users processed
* Successfully provisioned users
* Failed provisions with error details
* Any errors encountered

### Log Files

* Stored in `logs/` directory
* Timestamped filenames (e.g., `provision_20241201_143022.log`)
* Detailed information about all API operations
* Error details and troubleshooting information

### JSON Output (Optional)

If `--output` is specified, results are saved as JSON with the following structure:

```json
{
  "provisioned": [
    {
      "success": true,
      "email": "[email protected]",
      "org_id": "org-123",
      "result": {
        "email": "[email protected]",
        "rolePublicId": "role-abc-123",
        "created": "2025-12-04T00:00:24Z"
      }
    }
  ],
  "failed": [
    {
      "success": false,
      "email": "[email protected]",
      "org_id": "org-123",
      "error": "User already exists",
      "status_code": 409
    }
  ],
  "skipped": [],
  "errors": []
}
```

## Exit Codes

* `0` - Success (all users provisioned successfully)
* `1` - Error (one or more users failed to provision or error occurred)
* `130` - Interrupted by user (Ctrl+C)

## Examples

### Example 1: Provision Single User

```bash
python provision_user_to_snyk.py \
  --token "abc123-def456-ghi789" \
  --org-id "org-12345" \
  --email "[email protected]" \
  --role-public-id "role-abc-123"
```

### Example 2: Provision Users from CSV

```bash
python provision_user_to_snyk.py \
  --token "abc123-def456-ghi789" \
  --org-id "org-12345" \
  --file "users.csv"
```

### Example 3: EU Region with JSON Output

```bash
python provision_user_to_snyk.py \
  --token "abc123-def456-ghi789" \
  --org-id "org-67890" \
  --file "users.json" \
  --region "SNYK-EU-01" \
  --output "provisioning_results.json"
```

### Example 4: Using Environment Variables

```bash
export SNYK_TOKEN="your-token-here"
python provision_user_to_snyk.py \
  --org-id "org-12345" \
  --email "[email protected]" \
  --role-public-id "role-abc-123"
```

### Example 5: File with Default Role

```bash
python provision_user_to_snyk.py \
  --token "abc123-def456-ghi789" \
  --org-id "org-12345" \
  --file "users.csv" \
  --role-public-id "role-abc-123"
```

## Important Notes

### Prerequisites for Provisioning

1. **User Must Not Exist**: The user being provisioned must not already exist in the Snyk system
2. **Personal Token Required**: The API must be called using a personal token (not a service account token)
3. **SSO Configuration**: The Snyk Group must have Single Sign-On (SSO) configured
4. **SSO Login**: Both the inviting user and the provisioned user must log in using SSO
5. **Permissions**: The inviting user must have the "Provision Users" permission

### Error Handling

The script handles common errors:
* **409 Conflict**: User already exists
* **401 Unauthorized**: Invalid token or insufficient permissions
* **404 Not Found**: Organization not found
* **429 Rate Limited**: Automatically retries after waiting
* **500+ Server Errors**: Retries with exponential backoff

## Security Considerations

* **Token Security**: Never commit API tokens to version control
* **Permissions**: Use tokens with minimal necessary permissions
* **Audit Trail**: All operations are logged for audit purposes
* **Read/Write Operations**: This script modifies Snyk organization memberships

## File Structure

```
provision_user_to_snyk.py  # Main script
README.md                   # This documentation
requirements.txt            # Python dependencies
logs/                       # Log files directory (created automatically)
```

## Troubleshooting

### Common Issues

1. **"User already exists" error**
   - The user is already in the Snyk system
   - Check if the user needs to be invited instead of provisioned

2. **"Insufficient permissions" error**
   - Verify your token has "Provision Users" permission
   - Ensure you're using a personal token, not a service account token

3. **"Organization not found" error**
   - Verify the organization ID is correct
   - Ensure your token has access to the organization

4. **Rate limiting**
   - The script automatically handles rate limiting
   - If issues persist, add delays between requests

## License

This project is licensed under the Apache License 2.0.

## Disclaimer

The authors are not responsible for any unintended consequences from using this script. Always test thoroughly and ensure proper permissions before running in production environments.

