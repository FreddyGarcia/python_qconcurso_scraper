import bs4
import csv
import requests
import logging

# define logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())

def catch_keyboard_interrupt(func):
    def inner(*args, **params):
        try:
            return func(*args, **params)
        except KeyboardInterrupt as ex:
            from sys import exit
            logger.warning('Execution ended by user')
            exit()
    
    return inner

class Scraper:

    USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.19 16.47 Safari/537.36'
    BASE_URL = 'https://www.qconcursos.com/'
    HEADERS = {'User-Agent': USER_AGENT}

    def __init__(self):
        # if there is any error, will be stored here
        self.errors = []

        self.session = requests.session()
        self.data = []
        self.authenticated = self.authenticate()

    def __del__(self):
        logger.info('!')
        #  display errors if happended
        if self.errors:
            logger.error('\nShowing errors:')

            for error in self.errors:
                logger.error('-> ' + error)

    def request(self, url: str) -> bs4.BeautifulSoup:
        '''
            get a page and return a bs object
        '''
        res = self.session.get(url, headers=self.HEADERS)
        html = Scraper.make_soup(res.text)
        return html

    def authenticate(self) -> bool:

        logger.info('- AUTHENTICATION ')
        LOGIN_URL = self.BASE_URL + 'conta/entrar'

        # enter in the authentation page
        soup = self.request(LOGIN_URL)

        # gets the authenticity token from the login page
        # it's necesary to perform the login
        input_token = soup.find(
            'input', {'name': 'authenticity_token',  'type': 'hidden'}
        )

        # if the token was not found, add the error
        # and conclude the authentation
        if not input_token:
            self.errors.append('Could\'t get the authentation token')
            return False

        # get the token from the page
        token = input_token.attrs['value']
        email = 'horst.mr@gmail.com'
        passw = '!Firma666'

        # using the user, password and token, perform the authentation
        payload = {
            'utf8': '',
            'authenticity_token': token,
            'user[email]': email,
            'user[password]': passw,
            'commit': 'Entrar'
        }

        # send the payload
        res = self.session.post(LOGIN_URL, headers=self.HEADERS, data=payload)

        # successful authentation will redirect to /usuario
        authenticated = '/usuario' in res.url

        return authenticated

    def get_next_page(self, soup: bs4.BeautifulSoup) -> str:

        # try to find the pagination nav
        pagination_element = soup.find('nav', {'class': 'js-pagination'})

        if pagination_element:
            # if found, we check if there is a next page
            next_page_element = pagination_element.find('a', {'rel': 'next'})

            # if found, we get the page url
            if next_page_element:
                next_page_url = next_page_element.attrs['href']
                return self.BASE_URL + next_page_url

        return None

    def get_search_count(self, soup: bs4.BeautifulSoup) -> int:
        results = soup.select_one('H2.q-page-results-title strong')
        if results:
            results = results.text
            results = results.replace('.', '')
            results = int(results)
            return results
        
        return 1

    @catch_keyboard_interrupt
    def search(self, query_url: str, page_no=1) -> bs4.BeautifulSoup:
        '''
            given a query, scan the page and extract the data
        '''
        if not self.authenticated:
            self.errors.append('Not authenticated')
            return []

        # get the page given the query
        search = self.request(query_url)

        if page_no == 1:
            search_count = self.get_search_count(search)
            logger.info(f'- - {search_count} questions found')

        logger.info(f'- - Getting Questions from page no {page_no}')

        # if no results, return empty list
        if Scraper.is_empty_search(search):
            self.errors.append('The given url has not questions')
            return []

        data = self.extract_data(search)

        # check if there is next page
        next_page = self.get_next_page(search)

        if next_page:
            # if so, append the results from it
            page_no += 1
            data += self.search(next_page, page_no)

        # we're done
        self.data = data
        return data

    def extract_data(self, soup: bs4.BeautifulSoup) -> list:

        question_items = soup.find_all('div', {'class': 'q-question-item'})
        results = []

        for question_item in question_items:
            question_info = question_item.find('div', {'class': 'q-question-info'})
            question_ano = question_info.find_all('span')[0]
            question_banca = question_info.find_all('span')[1]
            question_enunciation = question_item.find('div', {'class': 'q-question-enunciation'})

            question_ano_text = question_ano.text.replace('Ano:', '').strip()
            question_banca_text = question_banca.text.replace('Banca:', '').strip()
            question_enunciation_text = question_enunciation.text

            question_img = question_item.find('img').attrs['src'] if question_item.find('img') else ''

            row_data = {
                'ano': question_ano_text,
                'banca': question_banca_text,
                'enunciation': question_enunciation_text,
                'image' : question_img
            }

            letters = ('', 'a', 'b', 'c', 'd', 'e')
            for i in range(5):
                row_data['choice_' + letters[i + 1]] = ''

            question_options = question_item.find(
                'ul', {'class': 'q-question-options'}).find_all('li')

            if len(question_options) == 2:
                row_data['type'] = 'true-false'
            else:
                len_question_options = len(question_options)
                for i in range(len_question_options):
                    enum = question_options[i].find(
                        'div', {'class': 'q-item-enum'})
                    row_data['choice_' + letters[i + 1]
                             ] = enum.text if enum is not None else ''

                row_data['type'] = 'multiple'

            results.append(row_data)

        return results

    def export_to_csv(self, output_name: str) -> bool:

        logger.info('')
        logger.info('- EXPORTING ')
        # if no rows to export, log the error and exit
        if not self.data:
            self.errors.append('No data to export')
            return False

        with open(output_name, 'w', newline='') as csvfile:

            logger.info('- - Exporting resulsts')
            logger.info(f'- - Writing {len(self.data)} rows')

            # use the first row to generate the header
            fieldnames = self.data[0].keys()
            # define the csv writer
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            # write the header (Explicit is better than implicit. PEP20, The Zen of Python)
            writer.writeheader()
            # write the rows
            writer.writerows(self.data)

            return True

    @staticmethod
    def make_soup(html: str) -> bs4.BeautifulSoup:
        return bs4.BeautifulSoup(html, 'html.parser')

    @staticmethod
    def is_empty_search(soup: bs4.BeautifulSoup) -> bool:
        empty_alert = soup.find('div', {'class': 'alert-empty-search'})
        is_empty = empty_alert is not None
        return is_empty


if __name__ == "__main__":

    FILE_N = 'questions.csv'
    SEARCH = 'https://www.qconcursos.com/questoes-de-concursos/questoes?administrative_level_ids%5B%5D=8&difficulty%5B%5D=2&publication_year%5B%5D=2019'

    # create the scraper object
    scraper = Scraper()
    # perform the search.
    # after this, resulst are saved in the scraper object
    scraper.search(SEARCH)
    # proceed to export the resulst
    scraper.export_to_csv(FILE_N)

