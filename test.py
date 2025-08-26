from pymongo import MongoClient

client = MongoClient("mongodb://mongo:27017")

database = client.get_database("test")
movies = database.get_collection("movies")

query = {"title": "Baak to the Future", "asdf": "asdfasd", "asdfasdf":"asdfasdf"}
# movie = movies.insert_one(query)

movie = movies.find_one(query)

print(movie)
 
client.close()