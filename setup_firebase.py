#!/usr/bin/env python
"""
Firebase Setup Helper

This script helps set up Firebase credentials for the chat application.
It can either read credentials from a JSON file or from environment variables.
"""

import os
import json
import sys

def setup_firebase():
    """Set up Firebase credentials for the application"""
    print("Firebase Credentials Setup Helper")
    print("=================================")
    print("This script will help you configure Firebase credentials for your chat application.")
    print("")
    
    # Check if credentials are already set in environment variables
    if os.environ.get("FIREBASE_CREDENTIALS"):
        print("Firebase credentials already set in environment variables.")
        should_continue = input("Do you want to reconfigure? (y/n): ")
        if should_continue.lower() != 'y':
            print("Exiting without changes.")
            return
    
    # Ask for the credentials file or environment variable setup
    use_file = input("Do you have a Firebase service account JSON file? (y/n): ")
    
    if use_file.lower() == 'y':
        # Get the file path
        file_path = input("Enter the path to your Firebase service account JSON file: ")
        
        if not os.path.exists(file_path):
            print(f"Error: File not found at {file_path}")
            return
        
        try:
            # Read the file
            with open(file_path, 'r') as f:
                creds = json.load(f)
            
            # Copy the file to the application directory
            with open('firebase-credentials.json', 'w') as f:
                json.dump(creds, f, indent=2)
            
            print("Credentials file saved as 'firebase-credentials.json'")
            
            # Get the storage bucket name
            if 'project_id' in creds:
                default_bucket = f"{creds['project_id']}.appspot.com"
                bucket = input(f"Enter your Firebase storage bucket name (default: {default_bucket}): ")
                if not bucket:
                    bucket = default_bucket
            else:
                bucket = input("Enter your Firebase storage bucket name: ")
            
            # Set environment variables for the current session
            os.environ["FIREBASE_STORAGE_BUCKET"] = bucket
            
            # Create a .env file
            with open('.env', 'w') as f:
                f.write(f"FIREBASE_STORAGE_BUCKET={bucket}\n")
            
            print("Environment variables set and saved to .env file")
            
        except Exception as e:
            print(f"Error processing credentials file: {e}")
            return
    else:
        # Manual environment variable setup
        print("You'll need to set up the FIREBASE_CREDENTIALS environment variable manually.")
        print("To do this, you'll need to:")
        print("1. Go to the Firebase console (https://console.firebase.google.com)")
        print("2. Navigate to Project Settings > Service Accounts")
        print("3. Click 'Generate New Private Key'")
        print("4. Copy the contents of the JSON file")
        
        # Get the storage bucket name
        bucket = input("Enter your Firebase storage bucket name (example: your-project-id.appspot.com): ")
        
        if bucket:
            # Set environment variables for the current session
            os.environ["FIREBASE_STORAGE_BUCKET"] = bucket
            
            # Create a .env file
            with open('.env', 'w') as f:
                f.write(f"FIREBASE_STORAGE_BUCKET={bucket}\n")
            
            print("Storage bucket name set and saved to .env file")
            print("")
            print("For the credentials, you will need to set the FIREBASE_CREDENTIALS environment variable with:")
            print("export FIREBASE_CREDENTIALS='<your JSON credentials as a string>'")
        else:
            print("No storage bucket name provided. You'll need to set this up manually.")
    
    print("")
    print("Setup complete!")
    print("When deploying to Render or another hosting service, make sure to set these environment variables:")
    print("- FIREBASE_CREDENTIALS (if using the environment variable approach)")
    print("- FIREBASE_STORAGE_BUCKET")

if __name__ == "__main__":
    setup_firebase() 