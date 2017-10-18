import requests
from bs4 import BeautifulSoup as BS
import datetime as dt

#scrapes sunrise and sunset times from timeanddate.com URL
def get_times(url, class_type, class_name, now):
  try:
    r = requests.get(url, timeout=100000)
  except requests.exceptions.Timeout:
    print "timed out"
    sunrise = now.replace(hour=7,minute=00)
    sunset = now.replace(hour=20, minute=00)
    return sunrise, sunset

  soup = BS(r.content, 'html.parser')
  times = soup.find_all(class_type, {"class": class_name})
  split_times = [time.get_text().split()[0] for time in times]
  sunrise_H_M = [int(time) for time in split_times[0].split(':')]
  sunset_H_M = [int(time) for time in split_times[1].split(':')]
  sunrise = now.replace(hour=sunrise_H_M[0], minute=sunrise_H_M[1])
  sunset = now.replace(hour=sunset_H_M[0]+12, minute=sunset_H_M[1])
  return sunrise, sunset


if __name__ == "__main__":
  url = "https://www.timeanddate.com/sun/usa/salt-lake-city"
 
  now = dt.datetime.now()
  sunrise, sunset  = get_times(url, "span", "three", now)
  now = dt.datetime.now()

  print(sunrise, sunset)
  print(now > sunrise and now < sunset)


