# Legacy Tests

These are the original integration test scripts that test against a running server.

## Usage

Start the development server:
```bash
python manage.py runserver
```

Then run the tests:
```bash
python legacy_tests/test_api.py
python legacy_tests/test_new_features.py
```

**Note:** These scripts have been replaced by the proper pytest test suite in the `tests/` directory. They are kept here for reference only.
