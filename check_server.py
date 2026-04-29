import urllib.request

try:
    with urllib.request.urlopen('http://127.0.0.1:5000/') as response:
        print(response.status)
        print(response.read().decode('utf-8'))
except Exception as exc:
    print('ERROR', type(exc).__name__, exc)
