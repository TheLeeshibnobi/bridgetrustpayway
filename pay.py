
from dotenv import load_dotenv
import json

load_dotenv()  # Make sure this is at the top

import os
import requests
from datetime import datetime, timedelta
from supabase import create_client, Client

class Pay:
    """Contains methods required for the home template."""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

        # Email authentication
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.email_password = os.getenv('EMAIL_PASSWORD')

        # TuMeNy API config
        self.tumeny_api_key = os.getenv("TUMENY_API_KEY")
        self.tumeny_api_secret = os.getenv("TUMENY_API_SECRET")

        if not self.tumeny_api_key or not self.tumeny_api_secret:
            raise Exception("Missing TUMENY_API_KEY or TUMENY_API_SECRET in environment variables.")

        # Generate auth token
        self.tumeny_token, self.token_expiry = self.get_tumeny_auth_token()
        if not self.tumeny_token:
            raise Exception("Failed to acquire TuMeNy token.")
        print(f"TuMeNy token acquired: {self.tumeny_token[:10]}...")

        self.headers = {
            "Authorization": f"Bearer {self.tumeny_token}",
            "Content-Type": "application/json"
        }

    def get_tumeny_auth_token(self):
        url = "https://tumeny.herokuapp.com/api/token"
        headers = {
            "apiKey": self.tumeny_api_key,
            "apiSecret": self.tumeny_api_secret
        }

        try:
            response = requests.post(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            token = data.get("token")
            expire_at = data.get("expireAt")

            if not token:
                raise Exception("Token not found in response")

            if expire_at is None:
                raise Exception("expireAt not found in response")

            # Handle the datetime format returned by the API
            if isinstance(expire_at, dict) and 'date' in expire_at:
                # Parse the datetime string from the API response
                try:
                    expire_datetime_str = expire_at['date']
                    # Parse the datetime string - it's in UTC format
                    token_expiry = datetime.fromisoformat(expire_datetime_str.replace('Z', '+00:00'))
                    # Convert to local time if needed, or keep as UTC
                    print(f"Token expires at: {token_expiry} UTC")
                except (ValueError, KeyError) as e:
                    print(f"Warning: Could not parse expireAt datetime: {expire_at}, using 1 hour default")
                    token_expiry = datetime.now() + timedelta(hours=1)
            elif isinstance(expire_at, (int, float)):
                # Handle seconds format (fallback)
                token_expiry = datetime.now() + timedelta(seconds=int(expire_at))
            elif isinstance(expire_at, str):
                try:
                    # Try to parse as ISO format datetime string
                    token_expiry = datetime.fromisoformat(expire_at.replace('Z', '+00:00'))
                except ValueError:
                    try:
                        # Try to parse as seconds
                        expire_seconds = int(expire_at)
                        token_expiry = datetime.now() + timedelta(seconds=expire_seconds)
                    except ValueError:
                        print(f"Warning: Could not parse expireAt string '{expire_at}', using 1 hour default")
                        token_expiry = datetime.now() + timedelta(hours=1)
            else:
                print(f"Warning: Unexpected expireAt format: {type(expire_at)}, using 1 hour default")
                token_expiry = datetime.now() + timedelta(hours=1)

            return token, token_expiry

        except requests.RequestException as e:
            print(f"Failed to get TuMeNy auth token: {e}")
            return None, None

    def check_payment_status(self, payment_id):
        """
        Checks the status of a Tumeny payment.
        Returns a dictionary with status information instead of just boolean.
        """
        url = f"https://tumeny.herokuapp.com/api/v1/payment/{payment_id}"
        headers = {
            "Authorization": f"Bearer {self.tumeny_token}"
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            status = data.get("payment", {}).get("status", "").upper()

            # Return structured status information
            if status == "SUCCESS":
                return {"status": "success", "completed": True}
            elif status in ["CANCELLED", "CANCELED", "FAILED", "DECLINED"]:
                return {"status": "failed", "completed": True, "reason": status.lower()}
            else:
                # Still pending or unknown status
                return {"status": "pending", "completed": False}

        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to check payment status: {e}")
            return {"status": "error", "completed": True, "reason": "api_error"}

    def initiate_payment(self, number, total_amount, transaction_fees, month, loan_id, organisation_name,
                         organisation_email):
        """
        Initiates payment using the TuMeNy payment API.

        Args:
            number (str): Phone number of the borrower.
            total_amount (float): Total amount to be paid.
            transaction_fees (float): Associated transaction fees.
            month (str): Payment month (e.g., "August 2025").
            loan_id (str): Loan identifier.
            organisation_name (str): Name of the organization.
            organisation_email (str): Contact email for the organization.

        Returns:
            dict: Response from the TuMeNy API, or error information.
        """
        try:
            # Step 1: Check if token is expired
            if self.tumeny_token is None or datetime.now() >= self.token_expiry:
                print("Token expired or missing, getting new token...")
                self.tumeny_token, self.token_expiry = self.get_tumeny_auth_token()
                if not self.tumeny_token:
                    return {"error": "auth_failed", "message": "Failed to get authentication token"}

            # Step 2: Format phone number - ensure it has country code
            formatted_number = number
            print(f"Using phone number: {formatted_number}")

            print(f"Formatted phone number: {formatted_number}")

            # Step 3: Prepare headers and payload according to API docs
            headers = {
                "Authorization": f"Bearer {self.tumeny_token}",
                "Content-Type": "application/json"
            }


            amount_in_kwacha = int(total_amount) if isinstance(total_amount, int) else int(total_amount)

            # According to the API docs, the correct structure should be:
            payload = {
                "description": f"{organisation_name} {month} payment for loan {loan_id}",
                "customerFirstName": "Customer",  # You might want to get this from borrower data
                "customerLastName": "Name",  # You might want to get this from borrower data
                "email": organisation_email,
                "phoneNumber": formatted_number,
                "amount": amount_in_kwacha  # Amount in kwacha, not ngwee
            }

            print("Sending payment request to TuMeNy:")
            print(f"  URL: https://tumeny.herokuapp.com/api/v1/payment")
            print(f"  Headers: {headers}")
            print(f"  Payload: {payload}")

            # Step 4: Make request to the correct endpoint
            response = requests.post("https://tumeny.herokuapp.com/api/v1/payment",
                                     headers=headers,
                                     json=payload,
                                     timeout=30)  # Add timeout

            print(f"Response status code: {response.status_code}")
            print(f"Response headers: {dict(response.headers)}")

            # Try to get response content regardless of status code
            try:
                response_text = response.text
                print(f"Response text: {response_text}")
            except:
                print("Could not get response text")

            # Step 5: Handle response
            if response.status_code == 200:
                try:
                    response_json = response.json()
                    print(f"Payment request successful: {response_json}")
                    return response_json
                except ValueError as e:
                    print(f"Failed to parse JSON response: {e}")
                    return {"error": "json_parse_error", "message": "Invalid JSON response from API"}
            else:
                error_message = f"HTTP {response.status_code}"
                try:
                    # Try to get error details from response
                    error_response = response.json()
                    error_message = error_response.get('message', error_message)
                except:
                    error_message = response.text or error_message

                print(f"Payment failed: {response.status_code} - {error_message}")
                return {"error": response.status_code, "message": error_message}

        except requests.exceptions.Timeout:
            print("Payment request timed out")
            return {"error": "timeout", "message": "Payment request timed out"}
        except requests.exceptions.ConnectionError:
            print("Connection error during payment request")
            return {"error": "connection_error", "message": "Could not connect to payment gateway"}
        except Exception as e:
            print(f"Payment initiation exception: {e}")
            import traceback
            traceback.print_exc()
            return {"error": "exception", "message": str(e)}

    def calculate_components(
            self,
            loan_id,
            loan_amount,
            monthly_payment,
            interest_rate,
            method
    ):
        """
        Calculates payment components for a single loan based on method.

        Args:
            loan_id (str): ID of the loan.
            loan_amount (float): Original loan amount.
            monthly_payment (float): Monthly payment amount.
            interest_rate (float): Annual interest rate as a decimal (e.g., 0.3 for 30%).
            method (str): Either 'simple' or 'amortisation'.

        Returns:
            dict: {
                'monthly_payment': float,
                'principal_component': float,
                'interest_component': float,
                'new_balance': float
            }
        """

        method = method.lower()
        monthly_interest_rate = interest_rate / 12  # corrected here

        # Fetch the latest balance
        repayment_response = (
            self.supabase
            .table('loan_repayments')
            .select('balance')
            .eq('loan_id', loan_id)
            .order('created_at', desc=True)
            .limit(1)
            .execute()
        )

        if repayment_response.data:
            current_balance = float(repayment_response.data[0]['balance'])
        else:
            current_balance = loan_amount

        if method == 'simple':
            # Simple interest always on original loan amount
            interest_component = round(loan_amount * monthly_interest_rate, 2)

        elif method == 'amortisation':
            # Interest on current (declining) balance
            interest_component = round(current_balance * monthly_interest_rate, 2)

        else:
            raise ValueError(f"Invalid repayment method '{method}' for loan {loan_id}")

        principal_component = round(monthly_payment - interest_component, 2)
        new_balance = round(current_balance - principal_component, 2)

        return {
            'monthly_payment': round(monthly_payment, 2),
            'principal_component': principal_component,
            'interest_component': interest_component,
            'new_balance': new_balance
        }

    def record_repayment(self, loan_id):
        """
        Record repayment in the loan_repayments table for a single loan.

        Args:
            loan_id (str): ID of the loan to process repayment for.

        Returns:
            dict: {
                'loan_id': str,
                'success': bool,
                'data': dict (if successful) or None,
                'error': str (if failed) or None
            }
        """
        try:
            # Fetch loan data
            loan_response = (
                self.supabase
                .table('loans')
                .select('*')
                .eq('id', loan_id)
                .execute()
            )

            if not loan_response.data:
                return {
                    'loan_id': loan_id,
                    'success': False,
                    'data': None,
                    'error': 'Loan not found'
                }

            loan_data = loan_response.data[0]

            # Fetch repayment method
            request_response = (
                self.supabase
                .table('loan_requests')
                .select('method')
                .eq('id', loan_id)
                .execute()
            )

            if not request_response.data:
                return {
                    'loan_id': loan_id,
                    'success': False,
                    'data': None,
                    'error': 'Method not found'
                }

            method = request_response.data[0]['method']
            monthly_payment = float(loan_data['monthly_payment'])

            # Calculate components
            repayment_components = self.calculate_components(
                loan_id=loan_id,
                loan_amount=loan_data['loan_amount'],
                monthly_payment=monthly_payment,
                interest_rate=loan_data['interest_rate'],
                method=method
            )

            # Prepare repayment data
            repayment_data = {
                'loan_id': loan_id,
                'payment_amount': monthly_payment,
                'principal_component': repayment_components['principal_component'],
                'interest_component': repayment_components['interest_component'],
                'balance': repayment_components['new_balance'],
                'payment_status': 'complete',
                'borrower_id': loan_data['borrower_id'],
                'organisation_id': loan_data['organisation_id']
            }

            # Insert repayment record
            repayment_response = self.supabase.table('loan_repayments').insert(repayment_data).execute()

            return {
                'loan_id': loan_id,
                'success': True,
                'data': repayment_response.data[0] if repayment_response.data else repayment_response.data,
                'error': None
            }

        except Exception as e:
            return {
                'loan_id': loan_id,
                'success': False,
                'data': None,
                'error': str(e)
            }

    def reduce_remaining_payments(self, loan_id):
        """Reduce the number of remaining payments for a given loan_id."""

        try:
            # Fetch current remaining payments
            loan_response = (
                self.supabase
                .table('loans')
                .select('remaining_payments')
                .eq('id', loan_id)
                .single()
                .execute()
            )

            if not loan_response.data:
                print(f"[ERROR] Loan with ID {loan_id} not found.")
                return False, f"Loan with ID {loan_id} not found."

            remaining_payments = loan_response.data.get('remaining_payments')

            if remaining_payments is None:
                print(f"[ERROR] 'remaining_payments' is missing in loan {loan_id}.")
                return False, f"'remaining_payments' missing for loan {loan_id}."

            if not isinstance(remaining_payments, int):
                try:
                    remaining_payments = int(remaining_payments)
                except ValueError:
                    print(f"[ERROR] 'remaining_payments' is not a valid integer for loan {loan_id}.")
                    return False, f"'remaining_payments' invalid for loan {loan_id}."

            if remaining_payments <= 0:
                print(f"[WARNING] Loan {loan_id} already has 0 remaining payments.")
                return False, f"Loan {loan_id} already complete."

            updated_remaining_payments = remaining_payments - 1

            # Update the value in the database
            update_response = (
                self.supabase
                .table('loans')
                .update({'remaining_payments': updated_remaining_payments})
                .eq('id', loan_id)
                .execute()
            )

            if update_response.data:
                return True, update_response.data
            else:
                print(f"[ERROR] Failed to update remaining payments for loan {loan_id}.")
                return False, "Update failed."

        except Exception as e:
            print(f"[EXCEPTION] reduce_remaining_payments: {e}")
            return False, str(e)


def test_tumeny_api():
    # Get credentials from environment
    api_key = os.getenv("TUMENY_API_KEY")
    api_secret = os.getenv("TUMENY_API_SECRET")

    if not api_key or not api_secret:
        print("❌ Missing TUMENY_API_KEY or TUMENY_API_SECRET")
        return

    print("🔑 Testing TuMeNy API credentials...")
    print(f"API Key: {api_key[:10]}...")
    print(f"API Secret: {api_secret[:10]}...")

    # Test 1: Get Auth Token
    print("\n📡 Step 1: Getting auth token...")

    token_url = "https://tumeny.herokuapp.com/api/token"
    token_headers = {
        "apiKey": api_key,
        "apiSecret": api_secret
    }

    try:
        response = requests.post(token_url, headers=token_headers, timeout=30)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code != 200:
            print("❌ Token request failed")
            return

        data = response.json()
        token = data.get("token")

        if not token:
            print("❌ No token in response")
            return

        print(f"✅ Token acquired: {token[:20]}...")

    except Exception as e:
        print(f"❌ Token request error: {e}")
        return

    # Test 2: Make a test payment request
    print("\n💰 Step 2: Testing payment request...")

    payment_url = "https://tumeny.herokuapp.com/api/v1/payment"
    payment_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Test payload - using minimal test data
    test_payload = {
        "description": "Test payment from API debugging",
        "customerFirstName": "Test",
        "customerLastName": "Customer",
        "email": "test@example.com",
        "phoneNumber": "0979991334",  # Test phone number
        "amount": 100  # 100 ngwee = 1 kwacha
    }

    print(f"Payment URL: {payment_url}")
    print(f"Headers: {payment_headers}")
    print(f"Payload: {json.dumps(test_payload, indent=2)}")

    try:
        response = requests.post(payment_url,
                                 headers=payment_headers,
                                 json=test_payload,
                                 timeout=30)

        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body: {response.text}")

        if response.status_code == 200:
            try:
                json_response = response.json()
                print(f"✅ Payment request successful!")
                print(f"Response JSON: {json.dumps(json_response, indent=2)}")
            except:
                print("⚠️  Response is not valid JSON")
        else:
            print(f"❌ Payment request failed with status {response.status_code}")

    except requests.exceptions.Timeout:
        print("❌ Payment request timed out")
    except requests.exceptions.ConnectionError:
        print("❌ Connection error")
    except Exception as e:
        print(f"❌ Payment request error: {e}")




