from flask import Flask, render_template, request, jsonify, g
import requests
import sqlite3

app = Flask(__name__)
apikey = "8c6a419"
DATABASE = "api.db" 

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Movie (
            imdbID TEXT PRIMARY KEY,
            title TEXT,
            year TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Country (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            flag_url TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS MovieCountry (
            Mid TEXT,
            Cname TEXT,
            FOREIGN KEY (Mid) REFERENCES Movie (imdbID),
            FOREIGN KEY (Cname) REFERENCES Country (name)
        )
    """)
    db.commit()

def searchfilms(search_text):
    url = f"https://www.omdbapi.com/?s={search_text}&apikey={apikey}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    print("Failed to retrieve search results.")
    return None

def getmoviedetails(movie):
    url = f"https://www.omdbapi.com/?i={movie['imdbID']}&apikey={apikey}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    print("Failed to retrieve movie details.")
    return None

def get_country_flag(fullname):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT flag_url FROM Country WHERE name = ?", (fullname,))
    row = cursor.fetchone()
    if row:
        return row["flag_url"]

    url = f"https://restcountries.com/v3.1/name/{fullname}?fullText=true"
    response = requests.get(url)
    if response.status_code == 200:
        country_data = response.json()
        if country_data:
            flag_url = country_data[0].get("flags", {}).get("svg", None)
            if flag_url:
                cursor.execute("INSERT OR IGNORE INTO Country (name, flag_url) VALUES (?, ?)", (fullname, flag_url))
                db.commit()
            return flag_url
    print(f"Failed to retrieve flag for country: {fullname}")
    return None

def merge_data_with_flags(filter):
    filmssearch = searchfilms(filter)
    moviesdetailswithflags = []

    if filmssearch and "Search" in filmssearch:
        for movie in filmssearch["Search"]:
            db = get_db()
            cursor = db.cursor()

            cursor.execute("SELECT * FROM Movie WHERE imdbID = ?", (movie["imdbID"],))
            movie_cached = cursor.fetchone()
            if not movie_cached:
                moviedetails = getmoviedetails(movie)
                if moviedetails:
                    cursor.execute("INSERT OR IGNORE INTO Movie (imdbID, title, year) VALUES (?, ?, ?)", 
                                   (moviedetails["imdbID"], moviedetails["Title"], moviedetails["Year"]))
                    countriesNames = moviedetails["Country"].split(",")
                    for country in countriesNames:
                        country_name = country.strip()
                        flag_url = get_country_flag(country_name)
                        cursor.execute("INSERT OR IGNORE INTO MovieCountry (Mid, Cname) VALUES (?, ?)", 
                                       (moviedetails["imdbID"], country_name))
            db.commit()

            cursor.execute("""
                SELECT m.title, m.year, mc.Cname, c.flag_url
                FROM Movie m
                JOIN MovieCountry mc ON m.imdbID = mc.Mid
                JOIN Country c ON mc.Cname = c.name
                WHERE m.imdbID = ?
            """, (movie["imdbID"],))
            rows = cursor.fetchall()

            if rows: 
                countries = [{"name": row["Cname"], "flag": row["flag_url"]} for row in rows]
                moviesdetailswithflags.append({"title": rows[0]["title"], "year": rows[0]["year"], "countries": countries})
    else:
        print("No results found for this search.")

    return moviesdetailswithflags

@app.route("/")
def index():
    filter = request.args.get("filter", "").upper()
    movies = merge_data_with_flags(filter)
    return render_template("index.html", movies=movies)

@app.route("/api/movies")
def api_movies():
    filter = request.args.get("filter", "")
    return jsonify(merge_data_with_flags(filter))

if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True)