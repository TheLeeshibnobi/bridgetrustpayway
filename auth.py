import os
from supabase import create_client, Client as SupabaseClient
from flask import session
from twilio.rest import Client as TwilioClient  # avoid name clash

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


    def check_organisation_number(self, phone):
        """checks if that number is in that organisations numbers"""
        try:
            response = (
                self.supabase
                .table('organisations')
                .select('org_phone_numbers')
                .filter('org_phone_numbers', 'cs', f'"{phone}"')  # 'cs' stands for "contains"
                .execute()
            )

            if response.data:
                print(f'{phone} exists in the database')
                return True
            else:
                print(f'{phone} does not exists in the database')

        except Exception as e:
            print(f"Error verifying OTP: {e}")
            return False


test = UserAuthentication()
print(test)






