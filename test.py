import requests

url = "https://bmtcmobileapi.karnataka.gov.in/WebAPI/SearchRoute_v2"
r = requests.post(url, json={"routetext": "210"})
print(r.status_code, r.text)
