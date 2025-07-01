import requests
from bs4 import BeautifulSoup



def getTitle(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    title = soup.title.string.replace(" - YouTube", "")
    return title

