import hashlib
import os
def generate_pwd(password):
    salt = os.urandom(16).hex()
    hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f"pbkdf2:sha256:600000${salt}${hash}"

print(generate_pwd('1130'))
