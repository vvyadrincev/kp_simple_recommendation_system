#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import lxml.html
import json
import datetime
import re
import collections
import pandas as pd

base_url = 'https://www.kinopoisk.ru'

counter = collections.Counter()

def get_html(response):
    if response.status_code != 200:
        return None
    else:
        return lxml.html.fromstring(response.content)
    
######################################################################################################################
        # ### Функции для скачивания расширенной информации о фильмах (заглядываем на страницу фильма) ###
######################################################################################################################
def make_movie_url(href):
    return ''.join((base_url,href))

def get_movie_html(href, session):
    return get_html(session.get(make_movie_url(href)))

def get_movies_ids_hrefs_to_process(filename_movies):
    movies = pd.read_csv(filename_movies, delimiter=';', header=0)
    movies_ids_hrefs = { (int(m[0]), m[1])  for m in movies.values}
    return movies_ids_hrefs

def parse_movie_html(html_movie):
    name_eng = html_movie.xpath("//span[@itemprop='alternativeHeadline']")
    name_eng = name_eng[0].text if len(name_eng) == 1 else ''

    name_rus = html_movie.xpath("//h1[@class='moviename-big']")
    name_rus = name_rus[0].text if len(name_rus) == 1 else ''

    rating = html_movie.xpath("//span[@class='rating_ball']")
    rating = float(rating[0].text) if len(rating) == 1 else -1.0

    rating_count = html_movie.xpath("//span[@class='ratingCount']")
    rating_count = int(''.join(rating_count[0].text.split())) if len(rating_count) == 1 else -1.0

    critics_rating = html_movie.xpath("//div[contains(@class,'criticsRating') or contains(@class,'criticsRatingDouble')]//div[@class='ratingNum']/span[@class='num']")
    critics_rating = int(critics_rating[0].text) if len(critics_rating) == 1 else -1

    imdb_rating = html_movie.xpath("//div[@class='block_2']/div[contains(text(),'IMDb:')]")
    if len(imdb_rating)==1:
        imdb_rating = imdb_rating[0]
        imdb_rating_count  = int(''.join(imdb_rating.text.split('(')[1].replace(')', '').split()))
        imdb_rating = float(imdb_rating.text.split()[1])
    else:
        imdb_rating_count = 0
        imdb_rating = -1.0

    year = html_movie.xpath("//table[@class='info']//td[@class='type' and contains(text(),'год')]/following-sibling::td//a")
    year = int(year[0].text) if len(year)==1 else 1900

    duration = html_movie.xpath("//table[@class='info']//td[@class='type' and contains(text(),'время')]/following-sibling::td/text()")
    if len(duration) >= 2:
        duration = int(duration[0].split()[0])
    else:
        duration = -1

    genres = {a.text for a in html_movie.xpath("//table[@class='info']//span[@itemprop='genre']/a")
              if a.text is not None
             }

    countries = {a.text for a in html_movie.xpath("//table[@class='info']//td[@class='type' and contains(text(),'страна')]/following-sibling::td/div/a")
                 if a.text is not None
                }

    return {
            'name_rus': name_rus,
            'name_eng': name_eng,
            'rating': rating,
            'rating_count': rating_count,
            'critics_rating': critics_rating,
            'imdb_rating': imdb_rating,
            'imdb_rating_count': imdb_rating_count,
            'year': year,
            'duration': duration,
            'genres': genres,
            'countries': countries
            }


######################################################################################################################
            # ### Функции для сохранения результатов краулинга информации о фильмах ###
######################################################################################################################
def generate_movie_line(movie):
    assert ('id' in movie and movie['id'] is not None)
    assert ('href' in movie and movie['href'] is not None)

    nameRus = movie["name_rus"]
    if nameRus is None:
        nameRus = ''
    elif nameRus.find(';') >=0:
        nameRus = '"{}"'.format(nameRus)
    
    nameEng = movie["name_eng"]
    if nameEng is None:
        nameEng = ''
    elif nameEng.find(';') >=0:
        nameEng = '"{}"'.format(nameEng)

    movie_genres_str = ','.join(list(movie['genres']))
    if movie_genres_str is None:
        movie_genres_str = ''
    elif movie_genres_str.find(';') >=0:
        movie_genres_str = '"{}"'.format(movie_genres_str)
    
    movie_countries_str = ','.join(list(movie['countries']))
    if movie_countries_str is None:
        movie_countries_str = ''
    elif movie_countries_str.find(';') >=0:
        movie_countries_str = '"{}"'.format(movie_countries_str)
    
    return "{};{};{};{};{};{};{};{};{};{};{};{};{}\n".format(
        movie['id'],movie['href'],nameRus,nameEng,movie['rating'],movie['rating_count'],
        movie['critics_rating'],movie['imdb_rating'], movie['imdb_rating_count'],
        movie['year'], movie['duration'], movie_genres_str,movie_countries_str
        )

def write_batch_movies(movies, filename_movies_extented):
    with open(filename_movies_extented, 'a', encoding='utf-8') as f:
        for movie in movies:
            f.write(generate_movie_line(movie))
            
def get_already_processed_movies(filename_movies_extented):
    movies = pd.read_csv(filename_movies_extented, delimiter=';', header=0)
    return {(int(m[0]), m[1]) for m in movies.values}

    
######################################################################################################################
                # ### Функции для скачивания информации о пользователях ###
######################################################################################################################
def make_user_url(i):
    #https://www.kinopoisk.ru/user/991122/
    return '/'.join((base_url,'user', str(i)))
    
def get_user_html(i, session):
    return get_html(session.get(make_user_url(i)))

def get_gender(ht):
    if isinstance(ht, (lxml.html.HtmlElement)):
        try:
            if len(ht.xpath("//span[@class='sex_female']")) > 0:
                return True
            elif len(ht.xpath("//span[@class='sex_male']")) > 0:
                return False
        except Exception as e:
            pass
    return None

def get_nickname(ht):
    if isinstance(ht, (lxml.html.HtmlElement)):
        try:
            return ht.xpath("//div[@class='nick_name' and @itemprop='name']")[0].text.strip()
        except Exception as e:
            pass
    return None

def get_location_info(ht):
    country, city = None, None
    if isinstance(ht, (lxml.html.HtmlElement)):
        try:
            country = ht.xpath("//a[@itemprop='homeLocation' and contains(@href,'community/country')]")[0].text.strip()
        except Exception as e:
            pass
        try:
            city = ht.xpath("//a[@itemprop='homeLocation' and contains(@href,'community/city')]")[0].text.strip()
        except Exception as e:
            pass
    return country, city

def get_birth_date(ht):
    month = 1
    day = 1
    year = 1900
    if isinstance(ht, (lxml.html.HtmlElement)):
        try:
            ht_elem = ht.xpath("//a[@itemprop='homeLocation' and contains(@href,'community/birth_day')]")[0]
            month_and_day = ht_elem.get('href').split('/')[-2].split('-')
            month = int(month_and_day[0])
            day = int(month_and_day[1])
        except Exception as e:
            pass
        try:
            year = int(ht.xpath("//a[@itemprop='homeLocation' and contains(@href,'community/birth_year')]")[0].text.strip())
        except Exception as e:
            pass
    return datetime.date(year, month, day)

def get_user_info(user_i, session):
    user_html = get_user_html(user_i, session)
    res = dict()
    res['nickname']   = get_nickname(user_html)
    if get_gender(user_html) is True:
        res['gender'] = 'female'
    elif get_gender(user_html) is False:
        res['gender'] = 'male'
    else:
        res['gender'] = None
    country, city     = get_location_info(user_html)
    res['country']    = country
    res['city']       = city
    res['birth_date'] = get_birth_date(user_html)
    return res

######################################################################################################################
                # ### Функции для скачивания оценок пользователей ###
######################################################################################################################

def make_votes_url(i, page):
#     https://www.kinopoisk.ru/user/4913930/votes/list/ord/date/vs/vote/page/2/#list
#     https://www.kinopoisk.ru/user/1007994/votes/list/ord/date/vs/vote/page/1/#list
    return '{}/user/{}/votes/list/ord/date/vs/vote/page/{}/#list'.format(base_url,
                                                                         str(i),
                                                                         str(page))

def get_votes_html(i, session, page):
    return get_html(session.get(make_votes_url(i, page)))

count_votes_patt = re.compile('\((\d+\s*(\d*))\)')
def extract_film_info_from_div(film):
    res = dict()
    
    try:
        info = film.xpath("./div[@class='info']")[0]
        res['href']    = info.xpath("./div[@class='nameRus']/a")[0].get('href').strip()
        res['vote']   = int(film.xpath("./div[@class='vote']")[0].text.strip())
    except Exception as e:
        counter['Extracting info, href, vote' + str(e)] += 1
        return res

    try:
        res['nameEng'] = info.xpath("./div[@class='nameEng']")[0].text.strip()
    except Exception as e:
        counter['Extracting nameEng: ' + str(e)] += 1
        
    try:
        res['nameRus'] = info.xpath("./div[@class='nameRus']/a")[0].text.strip()
    except Exception as e:
        counter['Extracting nameRus: ' + str(e)] += 1
        
    try:
        res['rating']  = float(info.xpath("//div[@class='rating']/b")[0].text.strip())
    except Exception as e:
        counter['Extracting rating: ' + str(e)] += 1

    try:
        count_votes    = info.xpath("./div[@class='rating']/span[@class='text-grey' and contains(text(), '(') and contains(text(),')')]")[0].text.strip()
        res['count_votes']  = int(''.join(re.match(count_votes_patt, count_votes).group(1).split()))
    except Exception as e:
        counter['Extracting count_votes: ' + str(e)] += 1
        
    try:
        res['duration'] = info.xpath("./div[@class='rating']/span[@class='text-grey' and not(contains(text(), '(')) and not(contains(text(),')'))]")[0].text.strip()
    except Exception as e:
        counter['Extracting duration: ' + str(e)] += 1


    try:
        res['date']   = film.xpath("./div[@class='date']")[0].text.strip()
    except Exception as e:
        counter['Extracting date: ' + str(e)] += 1        

    return res

def get_user_votes_for_films(user_i, session, start_page=1):
    html_votes = get_votes_html(user_i, session, 1)
    result = []
    films = html_votes.xpath("//div[@class='profileFilmsList']//div[@class='item' or @class='item even']")
    page = start_page
    try:
        count_of_votes = html_votes.xpath("//div[@class='pagesFromTo']")[0].text.split('из')[1].strip()
    except Exception as e:
        count_of_votes = None

    while len(films) > 0:
        curr_res = []
        for film in films:
            curr_res.append(extract_film_info_from_div(film))
        
        result.extend(curr_res)
        
        if count_of_votes is None:
            break
        elif count_of_votes.isdigit() and len(result) >= int(count_of_votes):
            break
        
        session.headers.update({
                'Referer' : make_votes_url(user_i, page),
            })
        page = page + 1
        html_votes = get_votes_html(user_i, session, page)
        films = html_votes.xpath("//div[@class='profileFilmsList']//div[@class='item' or @class='item even']")
        
    return {f['href']: f 
            for f in result 
            if 'vote' in f}

######################################################################################################################
                # ### Считывание списка user_id ###
######################################################################################################################
def read_users_set(filename):
    with open(filename, 'r') as f:
        return {int(u.strip()) for u in f.readlines()}

######################################################################################################################
                # ### Функции для сохранения результатов краулинга ###
######################################################################################################################
def write_batch_user_votes(users_batch_dict, votes_batch_dict,
                           already_saved_movies, 
                           out_filename_users, out_filename_votes, out_filename_movies):
    # {user_id: {'nickname': None,
    #           'gender': 'male',
    #           'country': None,
    #           'city': None,
    #           'birth_date': datetime.date(1900, 1, 1)},
    #  ...
    # }
    
    # {user_id: [{
    #             'nameRus': 'Вам и не снилось... (1980)',
    #             'href': '/film/vam-i-ne-snilos-1980-45660/',
    #             'rating': 8.191,
    #             'count_votes': 46370,
    #             'duration': '86 мин.',
    #             'nameEng': '',
    #             'date': '17.11.2015, 20:51',
    #             'vote': 10
    #             },
    #            ]
    #  ...
    # }
    with open(out_filename_users, 'a', encoding='utf-8') as f:
        for userid in users_batch_dict:
            nickname = users_batch_dict[userid]["nickname"] if users_batch_dict[userid]['nickname']  is not None else ''
            if nickname is not None and nickname.find(';') >=0:
                nickname = '"{}"'.format(nickname)
                
            country = users_batch_dict[userid]['country'] if users_batch_dict[userid]['country']  is not None else ''
            if country is not None and country.find(';') >=0:
                country = '"{}"'.format(country)
                
            city = users_batch_dict[userid]['city'] if users_batch_dict[userid]['city']  is not None else ''
            if city is not None and city.find(';') >=0:
                city = '"{}"'.format(city)
            
            f.write("{};{};{};{};{};{}\n".format(
                                    str(userid),
                                    nickname,
                                    users_batch_dict[userid]['gender'],
                                    country,
                                    city,
                                    users_batch_dict[userid]['birth_date']
                                )
                   )
    with open(out_filename_votes, 'a', encoding='utf-8') as fv:
        with open(out_filename_movies, 'a', encoding='utf-8') as fm:
            for userid in votes_batch_dict:
                for movie in votes_batch_dict[userid]:
                    href = movie["href"]
                    movie_id = int(href.split('/')[-2].split('-')[-1])
                    vote     = movie['vote']
                    date     = movie['date'] if 'date' in movie else ''
                    fv.write("{};{};{};{}\n".format(
                                str(userid), movie_id, vote, date
                            ) )

                    if movie_id not in already_saved_movies:
                        nameRus = ''
                        if 'nameRus' in movie:
                            nameRus = movie["nameRus"] if movie["nameRus"] is not None else ''
                            if nameRus is not None and nameRus.find(';') >=0:
                                nameRus = '"{}"'.format(nameRus)
                            
                        nameEng = ''
                        if 'nameEng' in movie:
                            nameEng = movie["nameEng"] if movie["nameEng"] is not None else ''
                            if nameEng is not None and nameEng.find(';') >=0:
                                nameEng = '"{}"'.format(nameEng)
                        
                        if 'rating' in movie and movie['rating'] is not None:
                            rating  = float(movie["rating"])
                        else:
                            rating = -1.0

                        if 'count_votes' in movie and movie['count_votes'] is not None:
                            count_votes  = int(movie["count_votes"])
                        else:
                            count_votes = -1
                        
                        duration = ''
                        if 'duration' in movie:
                            duration  = movie["duration"] if movie["duration"] is not None else ''
                            if duration is not None and duration.find(';') >=0:
                                duration = '"{}"'.format(duration)

                        fm.write("{};{};{};{};{};{};{}\n".format(
                                    movie_id, href, nameRus, nameEng, rating, count_votes, duration
                                ) )
                        
                        already_saved_movies.add(movie_id)