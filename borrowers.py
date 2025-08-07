import textwrap
from http.client import responses
import uuid
from datetime import datetime
import mimetypes

import bcrypt
from supabase import create_client, Client
from flask import session
import os
import random
import string
import smtplib
from email.message import EmailMessage


def get_content_type(file_extension):
    """Helper function to get content type based on file extension"""
    content_type, _ = mimetypes.guess_type(f"file{file_extension}")
    return content_type or "application/octet-stream"


class Borrowers:
    """contains methods required for the home template"""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

        # email authentication
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.email_password = os.getenv('EMAIL_PASSWORD')

    def get_borrower_by_loan(self, loan_id):
        """Gets the borrower information by loan_id."""

        try:
            # Step 1: Get borrower_id from the loans table
            loan_response = (
                self.supabase
                .table('loans')
                .select('borrower_id')
                .eq('id', loan_id)
                .single()
                .execute()
            )

            if not loan_response.data:
                print(f"[ERROR] Loan with ID {loan_id} not found.")
                return None

            borrower_id = loan_response.data.get('borrower_id')

            if not borrower_id:
                print(f"[ERROR] borrower_id not found for loan {loan_id}.")
                return None

            # Step 2: Get borrower details from borrowers table
            borrower_response = (
                self.supabase
                .table('borrowers')
                .select('*')
                .eq('id', borrower_id)
                .single()
                .execute()
            )

            if not borrower_response.data:
                print(f"[ERROR] Borrower with ID {borrower_id} not found.")
                return None

            return borrower_response.data

        except Exception as e:
            print(f"[EXCEPTION] get_borrower_by_loan failed: {e}")
            return None
