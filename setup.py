#!/usr/bin/env python
"""
Firebase Setup Helper

This script helps set up Firebase credentials for the chat application.
"""

import os
import json

print("Firebase Credentials Setup Helper")
print("=================================")
print("This script will help you configure Firebase credentials for your chat application.")
print("")

print("To set up Firebase:")
print("1. Create a Firebase project at https://console.firebase.google.com")
print("2. Enable Firestore Database and Storage")
print("3. Generate a service account key from Project Settings > Service Accounts")
print("4. Save the JSON file as 'firebase-credentials.json' in this directory")
print("5. Set the FIREBASE_STORAGE_BUCKET environment variable to your project's storage bucket")
print("   (usually 'your-project-id.appspot.com')")
print("")
print("When deploying to Render, set these environment variables:")
print("- FIREBASE_CREDENTIALS (the contents of your service account JSON as a string)")
print("- FIREBASE_STORAGE_BUCKET (your Firebase storage bucket name)") 