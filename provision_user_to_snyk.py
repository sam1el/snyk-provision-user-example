#!/usr/bin/env python3
"""
Snyk User Provisioning Script

This script provisions users to Snyk organizations using the Snyk API.
Users can be provisioned individually or in bulk from a CSV/JSON file.
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class SnykAPIClient:
    """Client for interacting with the Snyk API."""
    
    def __init__(self, token: str, region: str = "SNYK-US-01", version: str = "2025-11-05", debug: bool = False):
        """
        Initialize the Snyk API client.
        
        Args:
            token: Snyk API token
            region: Snyk region (SNYK-US-01, SNYK-US-02, SNYK-EU-01, SNYK-AU-01)
            version: API version
            debug: If True, enable debug logging
        """
        self.token = token
        self.version = version
        self.region = region
        self.debug = debug
        
        # Determine API base URL based on region
        region_map = {
            "SNYK-US-01": "https://api.snyk.io",
            "SNYK-US-02": "https://api.us.snyk.io",
            "SNYK-EU-01": "https://api.eu.snyk.io",
            "SNYK-AU-01": "https://api.au.snyk.io",
        }
        
        self.base_url = region_map.get(region, "https://api.snyk.io")
        self.headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Create a session with retry strategy for better reliability
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                     data: Optional[Dict] = None, json_data: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make an API request to Snyk.
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint path
            params: Query parameters
            data: Form data (for POST requests)
            json_data: JSON data (for POST requests)
            
        Returns:
            JSON response as dictionary, or None if error
        """
        url = f"{self.base_url}{endpoint}"
        
        if params is None:
            params = {}
        
        # Always include version parameter for GET requests and REST API POST requests
        # v1 API endpoints don't use version parameter
        if method.upper() == "GET" or (method.upper() == "POST" and endpoint.startswith("/rest/")):
            if "version" not in params:
                params["version"] = self.version
        
        try:
            # Log request details for debugging (only if debug is enabled)
            if self.debug:
                logging.debug(f"Making {method} request to: {url}")
                logging.debug(f"Params: {params}")
                logging.debug(f"Headers: {dict(self.session.headers)}")
                if json_data:
                    logging.debug(f"JSON body: {json_data}")
            
            response = self.session.request(
                method, 
                url, 
                params=params, 
                data=data,
                json=json_data,
                timeout=30
            )
            
            # Log response details (only if debug is enabled)
            if self.debug:
                logging.debug(f"Response status: {response.status_code}")
                logging.debug(f"Response headers: {dict(response.headers)}")
                logging.debug(f"Response body: {response.text[:500]}")  # First 500 chars
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logging.warning(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                # Retry once after rate limit
                response = self.session.request(
                    method, 
                    url, 
                    params=params, 
                    data=data,
                    json=json_data,
                    timeout=30
                )
            
            if response.status_code in [200, 201]:
                # Some endpoints return empty body on success
                if response.text:
                    return response.json()
                return {"status": "success"}
            elif response.status_code == 204:
                return {"status": "success", "message": "No content"}
            elif response.status_code == 400:
                # Handle 400 Bad Request
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", response.text) if isinstance(error_data, dict) else response.text
                    error_code = error_data.get("code") if isinstance(error_data, dict) else None
                except:
                    error_msg = response.text
                    error_code = None
                logging.error(f"Bad Request (400): {error_msg}")
                return {"error": error_msg, "status_code": 400, "error_type": "bad_request", "code": error_code}
            elif response.status_code == 403:
                # Handle 403 Forbidden - specific error for provision endpoint
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", response.text) if isinstance(error_data, dict) else response.text
                    error_code = error_data.get("code") if isinstance(error_data, dict) else None
                except:
                    error_msg = response.text
                    error_code = None
                logging.error(f"Forbidden (403): {error_msg}")
                return {"error": error_msg, "status_code": 403, "error_type": "forbidden", "code": error_code}
            elif response.status_code == 404:
                # Log full response for debugging
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", response.text) if isinstance(error_data, dict) else response.text
                    logging.warning(f"Resource not found (404): {endpoint}")
                    logging.warning(f"Full response: {response.text}")
                    logging.warning(f"Request URL: {url}")
                    logging.warning(f"Request method: {method}")
                    logging.warning(f"Request params: {params}")
                except:
                    error_msg = response.text
                    logging.warning(f"Resource not found (404): {endpoint}")
                    logging.warning(f"Full response: {response.text}")
                    logging.warning(f"Request URL: {url}")
                return {"error": error_msg, "status_code": 404, "error_type": "not_found", "response_text": response.text}
            elif response.status_code == 409:
                # Conflict - user may already exist
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", response.text) if isinstance(error_data, dict) else response.text
                except:
                    error_msg = response.text
                logging.warning(f"Conflict (409): {error_msg}")
                return {"error": error_msg, "status_code": 409, "error_type": "conflict"}
            else:
                error_msg = f"API request failed: {response.status_code} - {response.text}"
                logging.error(error_msg)
                return {"error": error_msg, "status_code": response.status_code, "error_type": "unknown"}
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Request exception: {str(e)}")
            return {"error": str(e)}
    
    def provision_user(self, org_id: str, email: str, role_public_id: str) -> Dict[str, Any]:
        """
        Provision a user to a Snyk organization.
        
        This endpoint allows you to add users to organizations at scale before their 
        first login, assigning them specific roles without requiring them to accept invitations.
        
        Prerequisites:
        - User must not already exist in the Snyk system
        - Must use a personal API token (not service account token)
        - Snyk Group must have SSO configured
        - Inviting user must have "Provision Users" permission
        - The API_KEY must not exceed the permissions being granted to the provisioned user
        
        Args:
            org_id: Snyk organization ID (required path parameter)
            email: User email address (required body parameter)
            role_public_id: ID of the role to grant this user (required body parameter)
            
        Returns:
            Dictionary with provisioning result containing:
            - success: Boolean indicating if provisioning was successful
            - email: User email address
            - org_id: Organization ID
            - result: API response data (if successful)
            - error: Error message (if failed)
            - status_code: HTTP status code (if failed)
            - error_type: Type of error (forbidden, conflict, not_found, etc.)
        """
        endpoint = f"/v1/org/{org_id}/provision"
        
        # Build request body according to Snyk API specification:
        # POST /v1/org/{orgId}/provision
        # Body parameters:
        #   - email (required, string): The email of the user
        #   - rolePublicId (required, string): ID of the role to grant this user
        body = {
            "email": email,
            "rolePublicId": role_public_id
        }
        
        logging.info(f"Provisioning user {email} to org {org_id} with rolePublicId {role_public_id}")
        if self.debug:
            logging.debug(f"Request endpoint: {endpoint}")
            logging.debug(f"Request body: {body}")
            logging.debug(f"Base URL: {self.base_url}")
            logging.debug(f"Full URL will be: {self.base_url}{endpoint}")
        
        result = self._make_request("POST", endpoint, json_data=body)
        
        if result and "error" not in result:
            logging.info(f"Successfully provisioned user {email}")
            return {
                "success": True,
                "email": email,
                "org_id": org_id,
                "result": result
            }
        else:
            error_msg = result.get("error", "Unknown error") if result else "No response from API"
            error_type = result.get("error_type", "unknown") if result else "unknown"
            status_code = result.get("status_code") if result else None
            
            # Provide helpful error messages based on error type
            if error_type == "forbidden":
                if "no user provision permission" in error_msg.lower() or "does not have permissions" in error_msg.lower():
                    error_msg = "API_KEY has no user provision permission or does not have permissions in role being provisioned"
                logging.error(f"Permission denied (403): {error_msg}")
            elif error_type == "conflict":
                logging.warning(f"Conflict (409): User may already exist - {error_msg}")
            else:
                logging.error(f"Failed to provision user {email}: {error_msg}")
            
            return {
                "success": False,
                "email": email,
                "org_id": org_id,
                "error": error_msg,
                "status_code": status_code,
                "error_type": error_type,
                "code": result.get("code") if result else None
            }
    
    def list_pending_provisions(self, org_id: str) -> List[Dict]:
        """
        List pending user provisions for an organization.
        
        Retrieves a list of users that have been provisioned but not yet logged in.
        
        Args:
            org_id: Snyk organization ID
            
        Returns:
            List of pending provision objects
        """
        endpoint = f"/v1/org/{org_id}/provision"
        
        logging.info(f"Listing pending provisions for org {org_id}")
        result = self._make_request("GET", endpoint)
        
        if result and "error" not in result:
            # The response format may vary, return the result as-is
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "data" in result:
                return result["data"]
            else:
                return [result] if result else []
        else:
            logging.warning(f"Failed to list pending provisions: {result.get('error') if result else 'Unknown error'}")
            return []
    
    def delete_pending_provision(self, org_id: str, email: str) -> Dict[str, Any]:
        """
        Delete a pending user provision.
        
        Removes a pending provision request for a user who hasn't logged in yet.
        
        Args:
            org_id: Snyk organization ID
            email: User email address
            
        Returns:
            Dictionary with deletion result
        """
        endpoint = f"/v1/org/{org_id}/provision"
        params = {"email": email}
        
        logging.info(f"Deleting pending provision for {email} in org {org_id}")
        
        result = self._make_request("DELETE", endpoint, params=params)
        
        if result and "error" not in result:
            logging.info(f"Successfully deleted pending provision for {email}")
            return {
                "success": True,
                "email": email,
                "org_id": org_id,
                "result": result
            }
        else:
            error_msg = result.get("error", "Unknown error") if result else "No response from API"
            logging.error(f"Failed to delete pending provision for {email}: {error_msg}")
            return {
                "success": False,
                "email": email,
                "org_id": org_id,
                "error": error_msg,
                "status_code": result.get("status_code") if result else None
            }
    
    def get_organizations(self, group_id: Optional[str] = None) -> List[Dict]:
        """
        Get list of organizations, optionally filtered by group ID.
        
        Args:
            group_id: Optional Snyk group ID to filter organizations
            
        Returns:
            List of organization objects
        """
        if group_id:
            endpoint = f"/rest/groups/{group_id}/orgs"
        else:
            endpoint = "/rest/orgs"
        
        params = {"limit": 100}
        
        all_orgs = []
        next_url = None
        
        while True:
            if next_url:
                if next_url.startswith("/groups/") or next_url.startswith("/orgs"):
                    if not next_url.startswith("/rest"):
                        next_url = "/rest" + next_url
                url = f"{self.base_url}{next_url}"
                try:
                    response = requests.request("GET", url, headers=self.headers, timeout=30)
                    if response.status_code == 200:
                        response_data = response.json()
                    else:
                        logging.error(f"Pagination request failed: {response.status_code} - {response.text}")
                        break
                except requests.exceptions.RequestException as e:
                    logging.error(f"Pagination request exception: {str(e)}")
                    break
            else:
                response_data = self._make_request("GET", endpoint, params)
                if not response_data:
                    break
            
            if response_data and "data" in response_data:
                all_orgs.extend(response_data["data"])
                logging.debug(f"Fetched {len(response_data['data'])} orgs (total so far: {len(all_orgs)})")
            
            # Check for next page
            links = response_data.get("links", {})
            next_url = links.get("next")
            
            if not next_url:
                break
        
        return all_orgs
    
    def get_group_memberships(self, group_id: str, role_name: Optional[str] = None) -> List[Dict]:
        """
        Get group memberships, optionally filtered by role name.
        Handles pagination to fetch all results.
        
        Args:
            group_id: Snyk group ID
            role_name: Optional role name to filter by
            
        Returns:
            List of membership objects with included resources
        """
        endpoint = f"/rest/groups/{group_id}/memberships"
        params = {}
        
        if role_name:
            params["role_name"] = role_name
        
        # Use a higher limit to reduce number of pagination requests
        params["limit"] = 100
        
        all_memberships = []
        next_url = None
        
        while True:
            # Use next_url if available, otherwise make initial request
            if next_url:
                # next_url is a relative path like /groups/{group_id}/memberships?version=...&limit=10&starting_after=...
                # We need to prepend /rest to make it a full endpoint path
                if next_url.startswith("/groups/"):
                    next_url = "/rest" + next_url
                url = f"{self.base_url}{next_url}"
                try:
                    response = requests.request("GET", url, headers=self.headers, timeout=30)
                    if response.status_code == 200:
                        response_data = response.json()
                    else:
                        logging.error(f"Pagination request failed: {response.status_code} - {response.text}")
                        break
                except requests.exceptions.RequestException as e:
                    logging.error(f"Pagination request exception: {str(e)}")
                    break
            else:
                response_data = self._make_request("GET", endpoint, params)
                if not response_data:
                    break
            
            if response_data and "data" in response_data:
                all_memberships.extend(response_data["data"])
                logging.debug(f"Fetched {len(response_data['data'])} memberships (total so far: {len(all_memberships)})")
            
            # Check for next page
            links = response_data.get("links", {})
            next_url = links.get("next")
            
            if not next_url:
                logging.debug("No more pages to fetch")
                break
        
        logging.debug(f"Total group memberships fetched: {len(all_memberships)}")
        return all_memberships
    
    def find_user_in_group(self, group_id: str, email: str) -> Optional[Dict]:
        """
        Find a user in group memberships by email address.
        
        Args:
            group_id: Snyk group ID
            email: User email address to search for
            
        Returns:
            User membership object if found, None otherwise
        """
        memberships = self.get_group_memberships(group_id)
        search_email = email.lower()
        
        if self.debug:
            logging.debug(f"Searching for email: {search_email} in {len(memberships)} memberships")
        
        for membership in memberships:
            # Extract user data from relationships
            # Structure: relationships.user.data.attributes.email
            relationships = membership.get("relationships", {})
            user_data = relationships.get("user", {}).get("data", {})
            
            if not user_data:
                if self.debug:
                    logging.debug(f"Membership {membership.get('id')} has no user data")
                continue
            
            # Get user ID
            user_id = user_data.get("id")
            if not user_id:
                if self.debug:
                    logging.debug(f"Membership {membership.get('id')} has no user ID")
                continue
            
            # Extract email from user data attributes
            # The email is in relationships.user.data.attributes.email
            user_attributes = user_data.get("attributes", {})
            user_email = user_attributes.get("email") if user_attributes else None
            
            # If still no email, log the structure for debugging
            if not user_email:
                if self.debug:
                    logging.debug(f"User {user_id} has no email in attributes. User data structure: {json.dumps(user_data, indent=2)}")
                continue
            
            # Normalize email for comparison
            user_email_lower = str(user_email).lower() if user_email else ""
            
            if user_email_lower == search_email:
                if self.debug:
                    logging.debug(f"Found matching user: {user_email_lower} (user_id: {user_id})")
                return {
                    "membership_id": membership.get("id"),
                    "user_id": user_id,
                    "email": user_email_lower,
                    "name": user_attributes.get("name") if user_attributes else None,
                    "membership": membership
                }
        
        if self.debug:
            logging.debug(f"User {search_email} not found in group memberships")
        return None
    
    def create_org_membership(self, org_id: str, user_id: str, role_id: str) -> Dict[str, Any]:
        """
        Create an organization membership for a user with a role.
        
        POST /rest/orgs/{org_id}/memberships
        
        Args:
            org_id: Snyk organization ID
            user_id: User ID (from group membership)
            role_id: Role ID (role public ID) to assign
            
        Returns:
            Dictionary with membership creation result
        """
        endpoint = f"/rest/orgs/{org_id}/memberships"
        
        # Build request body according to Snyk API specification
        # Content-Type: application/vnd.api+json
        # Required structure:
        # {
        #   "data": {
        #     "type": "org_membership",
        #     "relationships": {
        #       "org": { "data": { "id": org_id, "type": "org" } },
        #       "user": { "data": { "id": user_id, "type": "user" } },
        #       "role": { "data": { "id": role_id, "type": "org_role" } }
        #     }
        #   }
        # }
        body = {
            "data": {
                "type": "org_membership",
                "relationships": {
                    "org": {
                        "data": {
                            "id": org_id,
                            "type": "org"
                        }
                    },
                    "user": {
                        "data": {
                            "id": user_id,
                            "type": "user"
                        }
                    },
                    "role": {
                        "data": {
                            "id": role_id,
                            "type": "org_role"
                        }
                    }
                }
            }
        }
        
        # Update headers for REST API (JSON:API format)
        original_content_type = self.headers.get("Content-Type")
        original_accept = self.headers.get("Accept")
        
        self.headers["Content-Type"] = "application/vnd.api+json"
        self.headers["Accept"] = "application/vnd.api+json"
        self.session.headers.update(self.headers)
        
        try:
            logging.info(f"Creating org membership for user {user_id} in org {org_id} with role {role_id}")
            # REST API requires version parameter
            params = {"version": self.version}
            result = self._make_request("POST", endpoint, params=params, json_data=body)
            
            # Restore original headers
            self.headers["Content-Type"] = original_content_type
            self.headers["Accept"] = original_accept
            self.session.headers.update(self.headers)
            
            if result and "error" not in result:
                logging.info(f"Successfully created org membership for user {user_id}")
                return {
                    "success": True,
                    "user_id": user_id,
                    "org_id": org_id,
                    "role_id": role_id,
                    "result": result
                }
            else:
                error_msg = result.get("error", "Unknown error") if result else "No response from API"
                status_code = result.get("status_code") if result else None
                error_type = result.get("error_type") if result else None
                
                # Check if membership already exists (409 conflict) - this is a success case
                if status_code == 409 and error_type == "conflict":
                    # Parse JSON:API error format to check for "Membership already exists"
                    error_msg_lower = str(error_msg).lower()
                    if "membership already exists" in error_msg_lower:
                        logging.info(f"User {user_id} already has membership in org {org_id} - treating as success")
                        return {
                            "success": True,
                            "user_id": user_id,
                            "org_id": org_id,
                            "role_id": role_id,
                            "already_exists": True,
                            "result": {"status": "already_exists", "message": "Membership already exists"}
                        }
                
                logging.error(f"Failed to create org membership: {error_msg}")
                return {
                    "success": False,
                    "user_id": user_id,
                    "org_id": org_id,
                    "role_id": role_id,
                    "error": error_msg,
                    "status_code": status_code
                }
        except Exception as e:
            # Restore original headers on error
            self.headers["Content-Type"] = original_content_type
            self.headers["Accept"] = original_accept
            self.session.headers.update(self.headers)
            raise


class UserProvisioner:
    """Main class for provisioning users to Snyk organizations."""
    
    def __init__(self, client: SnykAPIClient):
        """
        Initialize the user provisioner.
        
        Args:
            client: SnykAPIClient instance
        """
        self.client = client
        self.results = {
            "provisioned": [],
            "org_memberships": [],
            "already_added": [],
            "failed": [],
            "skipped": [],
            "errors": []
        }
    
    def provision_single_user(self, org_id: str, email: str, role_public_id: str, 
                             group_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Provision a single user to an organization with fallback workflow.
        
        Workflow:
        1. Try to provision user using /v1/org/{org_id}/provision endpoint
        2. If successful (200/201), return success
        3. If 403 with "already provisioned" error, find user in group and create org membership
        4. Handle other errors appropriately
        
        Args:
            org_id: Snyk organization ID
            email: User email address
            role_public_id: ID of the role to grant this user (required)
            group_id: Optional group ID for fallback workflow (required if user already exists)
            
        Returns:
            Provisioning result dictionary
        """
        # Step 1: Try to provision user
        logging.info(f"Attempting to provision user {email} to org {org_id}")
        result = self.client.provision_user(org_id, email, role_public_id)
        
        # Step 2: If successful, we're done
        if result["success"]:
            logging.info(f"Successfully provisioned user {email} via provision endpoint")
            self.results["provisioned"].append(result)
            time.sleep(0.2)
            return result
        
        # Step 3: Check if user already exists in platform (403 with specific message)
        # Check for multiple error message patterns:
        # - "already provisioned" (original error code)
        # - "already exists in the platform" (new error message)
        error_msg_lower = result.get("error", "").lower()
        is_already_exists = (
            result.get("status_code") == 403 and
            (
                (result.get("code") == "84246666-373b-421a-9525-1ad740b3e787" and "already provisioned" in error_msg_lower) or
                "already exists in the platform" in error_msg_lower or
                "user already exists" in error_msg_lower
            )
        )
        
        if is_already_exists:
            logging.info(f"User {email} already exists in the platform. Attempting to add via org membership endpoint...")
            
            if not group_id:
                error_msg = "group_id is required when user is already provisioned. User cannot be added via provision endpoint."
                logging.error(error_msg)
                result["error"] = error_msg
                result["error_type"] = "missing_group_id"
                self.results["failed"].append(result)
                return result
            
            # Find user in group memberships
            logging.info(f"Searching for user {email} in group {group_id}")
            user_info = self.client.find_user_in_group(group_id, email)
            
            if not user_info:
                error_msg = f"User {email} not found in group {group_id} memberships"
                logging.error(error_msg)
                result["error"] = error_msg
                result["error_type"] = "user_not_found_in_group"
                self.results["failed"].append(result)
                return result
            
            logging.info(f"Found user {email} in group (user_id: {user_info['user_id']})")
            
            # Create org membership using REST API endpoint
            membership_result = self.client.create_org_membership(
                org_id, 
                user_info["user_id"], 
                role_public_id
            )
            
            if membership_result["success"]:
                # Store as org membership assignment (different from provisioned)
                result = {
                    "success": True,
                    "email": email,
                    "org_id": org_id,
                    "user_id": user_info["user_id"],
                    "role_id": membership_result.get("role_id"),
                    "method": "org_membership",
                    "already_exists": membership_result.get("already_exists", False),
                    "result": membership_result.get("result")
                }
                if membership_result.get("already_exists"):
                    logging.info(f"User {email} already has membership in org {org_id} - no action needed")
                    self.results["already_added"].append(result)
                else:
                    logging.info(f"Successfully added user {email} to org {org_id} via membership endpoint")
                    self.results["org_memberships"].append(result)
            else:
                logging.error(f"Failed to add user {email} via membership endpoint: {membership_result.get('error')}")
                result["error"] = membership_result.get("error", "Unknown error")
                result["error_type"] = "membership_creation_failed"
                self.results["failed"].append(result)
        
        # Step 4: Handle other errors (400 SSO connection, etc.)
        elif result.get("status_code") == 400:
            error_code = result.get("code")
            if error_code == "1b5315d9-23ac-4345-a4db-8d6baf579047":
                logging.error(f"SSO connection error: {result.get('error')}")
                result["error_type"] = "sso_connection_error"
            self.results["failed"].append(result)
        else:
            # Other errors (403 permission, 409 conflict, etc.)
            self.results["failed"].append(result)
        
        # Small delay to avoid rate limiting
        time.sleep(0.2)
        
        return result
    
    def provision_from_file(self, file_path: str, org_id: str, default_role_public_id: Optional[str] = None,
                           group_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Provision users from a CSV or JSON file.
        
        CSV format:
            email,role_public_id
            [email protected],role-abc-123
            [email protected],role-def-456
        
        JSON format:
            [
                {"email": "[email protected]", "role_public_id": "role-abc-123"},
                {"email": "[email protected]", "role_public_id": "role-def-456"}
            ]
        
        Args:
            file_path: Path to CSV or JSON file
            org_id: Snyk organization ID
            default_role_public_id: Default role public ID if not specified in file (optional)
            
        Returns:
            Summary dictionary
        """
        users = []
        
        # Determine file type and parse
        if file_path.endswith('.csv'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        email = row.get('email', '').strip()
                        role_public_id = row.get('role_public_id', '').strip() or default_role_public_id
                        if email:
                            if not role_public_id:
                                error_msg = f"Missing role_public_id for user {email}. role_public_id is required."
                                logging.error(error_msg)
                                self.results["errors"].append(error_msg)
                                continue
                            users.append({
                                'email': email,
                                'role_public_id': role_public_id
                            })
            except Exception as e:
                error_msg = f"Error reading CSV file: {str(e)}"
                logging.error(error_msg)
                self.results["errors"].append(error_msg)
                return {"error": error_msg}
        
        elif file_path.endswith('.json'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            email = item.get('email', '').strip()
                            role_public_id = item.get('role_public_id') or default_role_public_id
                            if email:
                                if not role_public_id:
                                    error_msg = f"Missing role_public_id for user {email}. role_public_id is required."
                                    logging.error(error_msg)
                                    self.results["errors"].append(error_msg)
                                    continue
                                users.append({
                                    'email': email,
                                    'role_public_id': role_public_id
                                })
                    else:
                        error_msg = "JSON file must contain an array of user objects"
                        logging.error(error_msg)
                        self.results["errors"].append(error_msg)
                        return {"error": error_msg}
            except Exception as e:
                error_msg = f"Error reading JSON file: {str(e)}"
                logging.error(error_msg)
                self.results["errors"].append(error_msg)
                return {"error": error_msg}
        else:
            error_msg = "Unsupported file format. Use CSV or JSON."
            logging.error(error_msg)
            self.results["errors"].append(error_msg)
            return {"error": error_msg}
        
        if not users:
            error_msg = "No valid users found in file"
            logging.warning(error_msg)
            return {"error": error_msg}
        
        logging.info(f"Found {len(users)} user(s) to provision from {file_path}")
        
        # Provision each user
        for idx, user in enumerate(users, 1):
            logging.info(f"Processing user {idx}/{len(users)}: {user['email']}")
            result = self.provision_single_user(
                org_id,
                user['email'],
                user['role_public_id'],
                group_id
            )
        
        return {
            "total": len(users),
            "provisioned": len(self.results["provisioned"]),
            "org_memberships": len(self.results["org_memberships"]),
            "already_added": len(self.results["already_added"]),
            "failed": len(self.results["failed"])
        }
    
    def get_results_summary(self) -> str:
        """Generate formatted results summary as a string."""
        lines = []
        lines.append("\n" + "="*80)
        lines.append("SNYK USER PROVISIONING RESULTS")
        lines.append("="*80)
        
        total_attempted = len(self.results["provisioned"]) + len(self.results["org_memberships"]) + len(self.results["already_added"]) + len(self.results["failed"])
        total_successful = len(self.results["provisioned"]) + len(self.results["org_memberships"]) + len(self.results["already_added"])
        
        lines.append(f"\nTotal Users Processed: {total_attempted}")
        lines.append(f"Successfully Provisioned: {len(self.results['provisioned'])}")
        lines.append(f"Org Membership Assignments: {len(self.results['org_memberships'])}")
        lines.append(f"Already Added (Membership Exists): {len(self.results['already_added'])}")
        lines.append(f"Failed: {len(self.results['failed'])}")
        
        if self.results["provisioned"]:
            lines.append("\n" + "-"*80)
            lines.append("SUCCESSFULLY PROVISIONED USERS:")
            lines.append("-"*80)
            for result in self.results["provisioned"]:
                lines.append(f"  ✓ {result['email']} → Org: {result['org_id']}")
                if "result" in result and isinstance(result["result"], dict):
                    created = result["result"].get("created", "N/A")
                    role = result["result"].get("role", "N/A")
                    lines.append(f"    Role: {role}, Created: {created}")
                lines.append("")
        
        if self.results["org_memberships"]:
            lines.append("\n" + "-"*80)
            lines.append("ORG MEMBERSHIP ASSIGNMENTS:")
            lines.append("-"*80)
            for result in self.results["org_memberships"]:
                lines.append(f"  ✓ {result['email']} → Org: {result['org_id']}")
                # Get role_id from stored result
                role = result.get("role_id", "N/A")
                # Extract created timestamp from API response (JSON:API format)
                created = "N/A"
                if "result" in result and isinstance(result["result"], dict):
                    # REST API uses JSON:API format: data.attributes.created
                    data = result["result"].get("data", {})
                    if isinstance(data, dict):
                        attributes = data.get("attributes", {})
                        if isinstance(attributes, dict):
                            created = attributes.get("created", "N/A")
                lines.append(f"    Role: {role}, Created: {created}")
                lines.append("")
        
        if self.results["already_added"]:
            lines.append("\n" + "-"*80)
            lines.append("ALREADY ADDED (MEMBERSHIP EXISTS):")
            lines.append("-"*80)
            for result in self.results["already_added"]:
                lines.append(f"  ✓ {result['email']} → Org: {result['org_id']}")
                # Get role_id from stored result
                role = result.get("role_id", "N/A")
                lines.append(f"    Role: {role}, Status: Already exists in org")
                lines.append("")
        
        if self.results["failed"]:
            lines.append("\n" + "-"*80)
            lines.append("FAILED PROVISIONS:")
            lines.append("-"*80)
            for result in self.results["failed"]:
                lines.append(f"  ✗ {result['email']} → Org: {result['org_id']}")
                error = result.get("error", "Unknown error")
                status_code = result.get("status_code", "N/A")
                error_type = result.get("error_type", "unknown")
                
                # Provide helpful context based on error type
                if error_type == "forbidden":
                    lines.append(f"    Error Type: Permission Denied (403)")
                    lines.append(f"    Message: {error}")
                    lines.append(f"    Note: API_KEY may lack user provision permission or permissions for the role")
                elif error_type == "conflict":
                    lines.append(f"    Error Type: Conflict (409)")
                    lines.append(f"    Message: {error}")
                    lines.append(f"    Note: User may already exist in the Snyk system")
                else:
                    lines.append(f"    Error: {error} (Status: {status_code})")
                lines.append("")
        
        if self.results["errors"]:
            lines.append("\n" + "-"*80)
            lines.append("ERRORS:")
            lines.append("-"*80)
            for error in self.results["errors"]:
                lines.append(f"  • {error}")
            lines.append("")
        
        # Total tally
        lines.append("\n" + "-"*80)
        lines.append("TOTAL SUMMARY:")
        lines.append("-"*80)
        lines.append(f"Total Successful: {total_successful} ({len(self.results['provisioned'])} provisioned + {len(self.results['org_memberships'])} org memberships + {len(self.results['already_added'])} already added)")
        lines.append(f"Total Failed: {len(self.results['failed'])}")
        lines.append(f"Total Processed: {total_attempted}")
        
        lines.append("="*80)
        return "\n".join(lines)
    
    def print_results(self, log_file: Optional[str] = None):
        """Print formatted results to console and log file."""
        summary = self.get_results_summary()
        print(summary)
        if log_file:
            try:
                with open(log_file, 'a') as f:
                    f.write(summary + "\n")
            except Exception as e:
                logging.warning(f"Could not write summary to log file: {str(e)}")


def setup_logging(log_dir: str = "logs", verbose: bool = False, debug: bool = False) -> str:
    """
    Set up logging to both console and file.
    
    Args:
        log_dir: Directory for log files
        verbose: If True, include DEBUG logs in file. If False, only INFO and above.
        debug: If True, show DEBUG logs in console as well
        
    Returns:
        Path to the log file
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"provision_{timestamp}.log")
    
    # Console handler - show DEBUG if debug flag is set, otherwise INFO and above
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # File handler - INFO and above by default, DEBUG and above if verbose
    file_handler = logging.FileHandler(log_file)
    file_level = logging.DEBUG if verbose else logging.INFO
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all levels, handlers filter
    root_logger.handlers = []  # Clear any existing handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    return log_file


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Provision users to Snyk organizations using the Snyk API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Provision a single user (with group-id for fallback)
  python provision_user_to_snyk.py --token YOUR_TOKEN --org-id ORG_ID --group-id GROUP_ID --email [email protected] --role-public-id role-abc-123
  
  # Provision users from CSV file
  python provision_user_to_snyk.py --token YOUR_TOKEN --org-id ORG_ID --group-id GROUP_ID --file users.csv
  
  # Provision users from JSON file with default role
  python provision_user_to_snyk.py --token YOUR_TOKEN --org-id ORG_ID --group-id GROUP_ID --file users.json --role-public-id role-abc-123
  
  # Use EU region
  python provision_user_to_snyk.py --token YOUR_TOKEN --org-id ORG_ID --group-id GROUP_ID --email [email protected] --role-public-id role-abc-123 --region SNYK-EU-01
        """
    )
    
    parser.add_argument(
        "--token",
        default=os.environ.get("SNYK_TOKEN") or os.environ.get("PERSONAL_SNYK_TOKEN"),
        help="Snyk API token (can also be set via SNYK_TOKEN or PERSONAL_SNYK_TOKEN environment variable)"
    )
    
    parser.add_argument(
        "--org-id",
        required=True,
        help="Snyk organization ID"
    )
    
    parser.add_argument(
        "--group-id",
        help="Snyk group ID (required for fallback workflow when user is already provisioned)"
    )
    
    parser.add_argument(
        "--email",
        help="User email address (for single user provisioning)"
    )
    
    parser.add_argument(
        "--file",
        help="Path to CSV or JSON file containing users to provision"
    )
    
    parser.add_argument(
        "--role-public-id",
        required=False,
        help="ID of the role to grant this user (required for single user provisioning, optional for file-based provisioning with default)"
    )
    
    parser.add_argument(
        "--region",
        default="SNYK-US-01",
        choices=["SNYK-US-01", "SNYK-US-02", "SNYK-EU-01", "SNYK-AU-01"],
        help="Snyk region (default: SNYK-US-01)"
    )
    
    parser.add_argument(
        "--version",
        default="2025-11-05",
        help="API version (default: 2025-11-05)"
    )
    
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path for JSON results (optional)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        dest="verbose",
        help="Include detailed DEBUG logs in the log file"
    )
    
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        dest="debug",
        help="Show DEBUG logs in console and log file (implies --verbose)"
    )
    
    args = parser.parse_args()
    
    # Validate token
    if not args.token:
        parser.error("Snyk API token is required. Provide --token or set SNYK_TOKEN/PERSONAL_SNYK_TOKEN environment variable.")
    
    # Validate that either email or file is provided
    if not args.email and not args.file:
        parser.error("Either --email or --file must be provided.")
    
    if args.email and args.file:
        parser.error("Provide either --email or --file, not both.")
    
    # Validate role_public_id is provided for single user provisioning
    if args.email and not args.role_public_id:
        parser.error("--role-public-id is required when provisioning a single user with --email.")
    
    # If debug is set, also enable verbose logging
    verbose = args.verbose or args.debug
    
    # Set up logging
    log_file = setup_logging(verbose=verbose, debug=args.debug)
    logging.info("Starting Snyk user provisioning")
    logging.info(f"Organization ID: {args.org_id}")
    if args.group_id:
        logging.info(f"Group ID: {args.group_id}")
    logging.info(f"Region: {args.region}")
    logging.info(f"API Version: {args.version}")
    if args.debug:
        logging.debug("Debug mode enabled - detailed logging active")
    
    try:
        # Initialize API client with debug flag
        client = SnykAPIClient(args.token, args.region, args.version, debug=args.debug)
        
        # Initialize provisioner
        provisioner = UserProvisioner(client)
        
        # Provision user(s)
        if args.email:
            logging.info(f"Provisioning single user: {args.email}")
            result = provisioner.provision_single_user(
                args.org_id,
                args.email,
                args.role_public_id,
                args.group_id if args.group_id else None
            )
        else:
            logging.info(f"Provisioning users from file: {args.file}")
            result = provisioner.provision_from_file(
                args.file,
                args.org_id,
                args.role_public_id if args.role_public_id else None,
                args.group_id if args.group_id else None
            )
        
        # Print results
        provisioner.print_results(log_file=log_file)
        
        # Save to file if requested
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(provisioner.results, f, indent=2)
            logging.info(f"Results saved to {args.output}")
        
        logging.info(f"Log file: {log_file}")
        
        # Exit with appropriate code
        if provisioner.results["failed"] or provisioner.results["errors"]:
            sys.exit(1)  # Exit with error if any failures
        else:
            sys.exit(0)  # Success
        
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

