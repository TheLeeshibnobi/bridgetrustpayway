import os
from supabase import create_client, Client as SupabaseClient
from flask import session
from twilio.rest import Client as TwilioClient  # avoid name
import re

class UserAuthentication:
    def __init__(self):
        # Supabase setup
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: SupabaseClient = create_client(url, service_role_key)

        # Twilio Verify setup
        self.twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.twilio_service_sid = os.getenv("TWILIO_SERVICE_SID")

        if not self.twilio_account_sid or not self.twilio_auth_token or not self.twilio_service_sid:
            raise ValueError("Missing Twilio environment variables.")

        self.twilio_client = TwilioClient(self.twilio_account_sid, self.twilio_auth_token)

    def send_otp(self, to_phone):
        """Send an OTP to the user's phone using Twilio Verify Default Template"""
        try:
            verification = self.twilio_client.verify.v2.services(self.twilio_service_sid).verifications.create(
                to=to_phone,
                channel="sms"
            )
            return verification.status == "pending"
        except Exception as e:
            print(f"Error sending OTP: {e}")
            return False

    def verify_otp(self, to_phone, code) -> bool:
        """Check if the user-provided code matches the one sent"""
        try:
            verification_check = self.twilio_client.verify.v2.services(self.twilio_service_sid).verification_checks.create(
                to=to_phone,
                code=code
            )
            return verification_check.status == "approved"
        except Exception as e:
            print(f"Error verifying OTP: {e}")
            return False



    def clean_phone_number(self, phone):
        phone = phone.strip()
        # Keep + at the beginning if it exists, then keep only digits
        if phone.startswith('+'):
            cleaned = '+' + re.sub(r'\D', '', phone[1:])  # keep +, remove non-digits after
        else:
            cleaned = re.sub(r'\D', '', phone)  # remove all non-digits

        return cleaned

    def check_organisation_number(self, phone):
        """Checks if that number is in an organisation's phone numbers array and returns the organisation ID if found."""
        try:
            cleaned_phone = self.clean_phone_number(phone)

            print(f"Original phone: {phone}")
            print(f"Cleaned phone: {cleaned_phone}")

            response = (
                self.supabase
                .table('organisations')
                .select('id, org_phone_numbers')
                .filter('org_phone_numbers', 'cs', f'{{{cleaned_phone}}}')  # Array format
                .execute()
            )

            if response.data:
                organisation_id = response.data[0]['id']
                print(f'{cleaned_phone} exists in the database under organisation ID {organisation_id}')
                return True, organisation_id
            else:
                print(f'{cleaned_phone} does not exist in the database')
                return False, None

        except Exception as e:
            print(f"Error checking phone number: {e}")
            return False, None









