import inspect
import database
import blueprints.transactions

print("database.query signature:", inspect.signature(database.query))
print("blueprints.transactions.query signature:", inspect.signature(blueprints.transactions.query))
