# Data Samples

## 1. Routes

```bash
curl 'https://bmtcmobileapi.karnataka.gov.in/WebAPI/SearchRoute_v2' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36' \
  -H 'lan: en' \
  --data-raw '{"routetext":"210"}'
```


## 2. Route points

```bash
curl -X POST 'https://bmtcmobileapi.karnataka.gov.in/WebAPI/RoutePoints' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36' \
  -d '{"routeid":3796}'
```


## 3. Vehicles

```bash
curl 'https://bmtcmobileapi.karnataka.gov.in/WebAPI/ListVehicles' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36' \
  --data-raw '{"vehicleRegNo":"0007"}'
```

## 4. Vehicle Trip Details

```bash
curl 'https://bmtcmobileapi.karnataka.gov.in/WebAPI/VehicleTripDetails_v2' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36' \
  --data-raw '{"vehicleId":21670}'
```

## 5. Time Tables

Time table by station details.

```bash
curl 'https://bmtcmobileapi.karnataka.gov.in/WebAPI/GetTimetableByStation_v4' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36' \
  -H 'lan: en' \
  --data-raw '{"fromStationId":36223,"toStationId":38888,"p_startdate":"2025-10-04 15:17","p_enddate":"2025-10-04 23:59","p_isshortesttime":2,"p_routeid":"","p_date":"2025-10-04 15:17"}'
```

Time table by route ID.

```bash
curl 'https://bmtcmobileapi.karnataka.gov.in/WebAPI/GetTimetableByRouteid_v3' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36' \
  -H 'lan: en' \
  --data-raw '{"current_date":"2025-10-04T18:30:00.000Z","routeid":3796,"starttime":"2025-10-04 15:17","endtime":"2025-10-04 23:59"}'
```


## 6. Route details

```bash
curl 'https://bmtcmobileapi.karnataka.gov.in/WebAPI/SearchByRouteDetails_v4' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36' \
  -H 'deviceType: WEB' \
  -H 'lan: en' \
  --data-raw '{"routeid":2116,"servicetypeid":0}'
```