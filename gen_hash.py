import os, binascii, hashlib
salt = binascii.hexlify(os.urandom(16)).decode('utf-8')
dk = hashlib.pbkdf2_hmac('sha256', b'1130', salt.encode('utf-8'), 600000)
hash_str = f"pbkdf2:sha256:600000${salt}${binascii.hexlify(dk).decode('utf-8')}"
with open("hash.txt", "w") as f:
    f.write(hash_str)
