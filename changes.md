# Input validation
## SQL injection
all fields have single quotes replaced by html entities.
file upload has name made safe in similar fashion.

## XSS fix
Simple regex check for [^<>|] wtforms validator.

## Password is not empty and is equal to confirm-pwd field
used wtform.validators

## username is taken!


# Broken access control
## Implement sessions


# Database
## encrypted passwords
using flask-bcrypt (really just bcrypt) to hash passwords before storing in sql.