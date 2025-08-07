import textwrap
from http.client import responses

import bcrypt
from supabase import create_client, Client
from flask import session
import os
import random
import string
import smtplib
from email.message import EmailMessage


class Organisations:
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


    def get_organisational_name(self, organisation_id):
        """gets the organizational name using the id"""
        try:
            organisation_response = (
                self.supabase
                .table('organisations')
                .select('id','name', 'email')
                .eq('id', organisation_id)
                .execute()
            )

            return organisation_response.data[0]['name'], organisation_response.data[0]['email']

        except Exception as e:
            print(f'Exception: {e}')


    def get_organisations(self):
        """returns a list of organizations"""
        try:
            organisation_response = (
                self.supabase
                .table('organisations')
                .select('name', 'id', 'email')
                .execute()
            )

            return organisation_response.data

        except Exception as e:
            print(f'Exception: {e}')


