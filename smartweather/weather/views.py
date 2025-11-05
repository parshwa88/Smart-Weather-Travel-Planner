from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import json
import requests
import datetime


# Weather view
def home(request):
    city = request.GET.get('city', 'Sangli')
    api_key = settings.OPENWEATHER_API_KEY
    error_message = None
    data = {}

    try:
        # Current weather
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
        response = requests.get(url).json()

        if response.get("cod") != 200:
            # City not found or invalid input
            error_message = response.get("message", "City not found. Please check the name and try again.")
        else:
            # Forecast
            forecast_url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={api_key}&units=metric"
            forecast_response = requests.get(forecast_url).json()

            # Current weather data
            data = {
                "city": response['name'],
                "temperature": response['main']['temp'],
                "feels_like": response['main']['feels_like'],
                "temp_min": response['main']['temp_min'],
                "temp_max": response['main']['temp_max'],
                "description": response['weather'][0]['description'],
                "icon": response['weather'][0]['icon'],
            }

            # Hourly forecast (next 6 intervals)
            hourly = []
            for entry in forecast_response['list'][:6]:
                hourly.append({
                    "time": entry['dt_txt'].split(" ")[1][:5],  # e.g. "12:00"
                    "temp": entry['main']['temp'],
                    "icon": entry['weather'][0]['icon'],
                    "rain": int(entry.get('pop', 0) * 100),  # % chance of rain
                })

            # Daily forecast (group by day)
            daily = {}
            for entry in forecast_response['list']:
                date = entry['dt_txt'].split(" ")[0]
                temp = entry['main']['temp']
                rain = int(entry.get('pop', 0) * 100)

                if date not in daily:
                    daily[date] = {
                        "min": temp,
                        "max": temp,
                        "rain": rain,
                        "icon": entry['weather'][0]['icon']
                    }
                else:
                    daily[date]["min"] = min(daily[date]["min"], temp)
                    daily[date]["max"] = max(daily[date]["max"], temp)
                    daily[date]["rain"] = max(daily[date]["rain"], rain)

            # Keep next 3 days
            forecast_daily = []
            today = datetime.date.today()
            for i, (date, vals) in enumerate(daily.items()):
                label = "Today" if i == 0 else "Tomorrow" if i == 1 else date
                forecast_daily.append({
                    "date": label,
                    "min": round(vals["min"]),
                    "max": round(vals["max"]),
                    "rain": vals["rain"],
                    "icon": vals["icon"]
                })
                if len(forecast_daily) >= 3:
                    break

            data["hourly"] = hourly
            data["forecast_daily"] = forecast_daily

    except requests.exceptions.RequestException:
        error_message = "Error fetching weather data. Please check your internet connection."
    except Exception:
        error_message = "An unexpected error occurred. Please try again later."

    return render(request, 'weather/home.html', {"data": data, "error_message": error_message})


# Smart Assistant endpoint (simple intent router)
@csrf_exempt
def assistant(request):
    if request.method != 'POST':
        return JsonResponse({
            "ok": False,
            "error": "Method not allowed"
        }, status=405)

    try:
        body_unicode = request.body.decode('utf-8') or '{}'
        payload = json.loads(body_unicode)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    message = (payload.get('message') or '').strip()
    city = (payload.get('city') or '').strip()

    if not message:
        return JsonResponse({"ok": False, "error": "Message is required"}, status=400)

    lower = message.lower()

    # Simple canned intents with city context
    if any(k in lower for k in ["hello", "hi", "hey"]):
        reply = "Hello! I can help with weather and travel planning. Ask me anything."
        if city:
            reply += f" Currently viewing weather for {city}."
    elif "rain" in lower or "rainy" in lower or "precipitation" in lower:
        if city:
            reply = f"For {city}, check the hourly forecast tiles above for rain probabilities. Each tile shows the percentage chance of precipitation."
        else:
            reply = "There's a chance of rain. Check the hourly forecast tiles for probabilities."
    elif any(k in lower for k in ["temp", "temperature", "hot", "cold", "warm"]):
        if city:
            reply = f"In {city}, the temperature details are shown on the main card. Check the current temp, feels like, and daily min/max ranges."
        else:
            reply = "Temperature details are shown on the left panel. Want me to check another city?"
    elif any(k in lower for k in ["forecast", "forecasts", "hourly", "daily", "tomorrow"]):
        if city:
            reply = f"For {city}, the hourly forecast shows the next 6 intervals, and the daily forecast shows the next 3 days with min/max temps and rain chances."
        else:
            reply = "Check the 'Hourly forecast' and 'Next 3 days' sections above for detailed forecast information."
    elif any(k in lower for k in ["route", "travel", "map", "traffic", "journey"]):
        reply = "Use the Smart Travel Planner above to enter origin and destination. I can help plan routes between cities!"
    elif any(k in lower for k in ["what can you do", "help", "capabilities", "features"]):
        reply = "I can help with: 1) Current weather information, 2) Hourly and daily forecasts, 3) Rain probabilities, 4) Temperature details, 5) Travel route planning. Just ask!"
    else:
        reply = "I understand. Can you be more specific? Try asking about weather, forecasts, rain, temperature, or travel routes."
        if city:
            reply += f" (Current city: {city})"

    return JsonResponse({
        "ok": True,
        "reply": reply
    })


# Geocoding search (Nominatim)
def geo_search(request):
    query = (request.GET.get('query') or '').strip()
    limit = int(request.GET.get('limit', '5'))

    if not query:
        return JsonResponse({"ok": False, "error": "query is required"}, status=400)

    try:
        nominatim_url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'jsonv2',
            'addressdetails': 1,
            'limit': limit
        }
        headers = { 
            'User-Agent': 'smartweather-smarttravel/1.0 (contact: user@example.com)' 
        }
        r = requests.get(nominatim_url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        results = r.json()

        places = []
        for item in results:
            try:
                places.append({
                    'name': item.get('display_name', ''),
                    'lat': float(item.get('lat', 0)),
                    'lng': float(item.get('lon', 0)),
                    'type': item.get('type', ''),
                    'class': item.get('class', ''),
                })
            except (ValueError, TypeError) as e:
                # Skip invalid entries
                continue

        return JsonResponse({"ok": True, "results": places})
    except requests.exceptions.RequestException as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=502)
    except Exception as e:
        return JsonResponse({"ok": False, "error": "geocoding_failed"}, status=500)


# Route planning (OSRM public demo)
@csrf_exempt
def route_plan(request):
    if request.method != 'POST':
        return JsonResponse({"ok": False, "error": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    origin = payload.get('origin')
    destination = payload.get('destination')
    profile = payload.get('mode', 'driving')  # driving, walking, cycling

    if not origin or not destination:
        return JsonResponse({"ok": False, "error": "origin and destination required"}, status=400)

    try:
        # OSRM demo server expects lon,lat
        o_lng, o_lat = origin['lng'], origin['lat']
        d_lng, d_lat = destination['lng'], destination['lat']
        osrm_url = f"https://router.project-osrm.org/route/v1/{profile}/{o_lng},{o_lat};{d_lng},{d_lat}"
        params = {'overview': 'simplified', 'geometries': 'geojson'}
        
        headers = { 'User-Agent': 'smartweather-smarttravel/1.0' }
        r = requests.get(osrm_url, params=params, headers=headers, timeout=12)
        r.raise_for_status()
        data = r.json()
        
        if data.get('code') != 'Ok' or not data.get('routes'):
            return JsonResponse({"ok": False, "error": "No route found between these locations"}, status=404)

        route = data['routes'][0]
        summary = {
            'distance_m': route['distance'],
            'duration_s': route['duration'],
            'geometry': route['geometry'],
        }
        return JsonResponse({"ok": True, "route": summary})
    except KeyError as e:
        return JsonResponse({"ok": False, "error": "Invalid coordinates format"}, status=400)
    except requests.exceptions.Timeout:
        return JsonResponse({"ok": False, "error": "Routing service timed out"}, status=504)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"ok": False, "error": "Routing service unavailable"}, status=502)
    except Exception as e:
        return JsonResponse({"ok": False, "error": "Unexpected routing error"}, status=500)
