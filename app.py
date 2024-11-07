from flask import Flask, render_template, request, jsonify
import requests
from concurrent.futures import ThreadPoolExecutor
from flask_caching import Cache

app = Flask(__name__)

# Configuración de cache (para mejorar el rendimiento)
app.config['CACHE_TYPE'] = 'simple'  # Usar un tipo de caché simple para desarrollo
cache = Cache(app)

apikey = "71bff71a"

# Número máximo de resultados por página
RESULTS_PER_PAGE = 10

# Cache para los resultados de películas y banderas
MOVIES_CACHE_KEY = "movies_cache"
FLAGS_CACHE_KEY = "flags_cache"


def searchfilms(search_text, page=1):
    """Busca películas con paginación en la API OMDb"""
    if not search_text:
        search_text = "a"  # Término común para obtener muchas películas

    # Revisar si la búsqueda ya está cacheada
    cache_key = f"search_{search_text}_{page}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result

    url = f"https://www.omdbapi.com/?s={search_text}&page={page}&apikey={apikey}"
    response = requests.get(url)
    print("Search URL:", url)

    if response.status_code == 200 and response.json().get("Response") == "True":
        result = response.json().get("Search")  # Devuelve solo la lista de películas
        cache.set(cache_key, result, timeout=60 * 5)  # Cachear la respuesta durante 5 minutos
        return result
    else:
        print("OMDb API returned an error:", response.json().get("Error"))
        return []


def getmoviedetails(movie):
    """Obtiene los detalles de una película usando su IMDb ID"""
    if "imdbID" not in movie:
        return None

    # Revisar si los detalles de la película ya están cacheados
    cache_key = f"movie_details_{movie['imdbID']}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result

    url = f"https://www.omdbapi.com/?i={movie['imdbID']}&apikey={apikey}"
    response = requests.get(url)

    if response.status_code == 200 and response.json().get("Response") == "True":
        result = response.json()
        cache.set(cache_key, result, timeout=60 * 10)  # Cachear los detalles de la película durante 10 minutos
        return result
    return None


def get_country_flag(fullname):
    """Obtiene la URL de la bandera de un país usando la API de RestCountries"""
    # Revisar si la bandera ya está cacheada
    cache_key = f"flag_{fullname}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result

    url = f"https://restcountries.com/v3.1/name/{fullname}?fullText=true"
    response = requests.get(url)

    if response.status_code == 200:
        country_data = response.json()
        if country_data:
            flag_url = country_data[0].get("flags", {}).get("svg", None)
            cache.set(cache_key, flag_url, timeout=60 * 60)  # Cachear la bandera durante 1 hora
            return flag_url
    return None


def fetch_flags(countries):
    """Obtiene las banderas de los países en paralelo"""
    with ThreadPoolExecutor() as executor:
        return {country: executor.submit(get_country_flag, country) for country in countries}


def merge_data_with_flags(filter, page=1):
    """Combina los datos de las películas con las banderas de los países"""
    filmssearch = searchfilms(filter, page)
    moviesdetailswithflags = []

    if filmssearch:
        countries_set = set()  # Para evitar consultas repetidas a la API de banderas
        movies = []
        for movie in filmssearch:
            moviedetails = getmoviedetails(movie)
            if moviedetails:
                countries_names = moviedetails["Country"].split(",")
                countries_set.update([country.strip() for country in countries_names])
                movies.append(moviedetails)

        # Obtener banderas en paralelo
        flags = fetch_flags(countries_set)

        # Agregar las banderas a los países
        for movie in movies:
            countries = []
            countries_names = movie["Country"].split(",")
            for country in countries_names:
                country = country.strip()
                flag_url = flags.get(country).result() if flags.get(country) else None
                countries.append({"name": country, "flag": flag_url})

            moviesdetailswithflags.append({
                "title": movie["Title"],
                "year": movie["Year"],
                "countries": countries
            })

    return moviesdetailswithflags


@app.route("/")
def index():
    filter = request.args.get("filter", "").strip().upper()
    page = int(request.args.get("page", 1))
    print(f"Page: {page}, Filter: {filter}")

    movies = merge_data_with_flags(filter, page)
    return render_template("index.html", movies=movies, page=page)


@app.route("/api/movies")
def api_movies():
    filter = request.args.get("filter", "")
    page = int(request.args.get("page", 1))
    return jsonify(merge_data_with_flags(filter, page))


if __name__ == "__main__":
    app.run(debug=True)
