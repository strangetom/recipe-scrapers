# mypy: disallow_untyped_defs=False
import inspect
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from recipe_scrapers.settings import settings

from ._grouping_utils import IngredientGroup
from ._schemaorg import SchemaOrg

# Some sites close their content for 'bots', so user-agent must be supplied
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:86.0) Gecko/20100101 Firefox/86.0"
}


class AbstractScraper:
    page_data: Union[str, bytes]

    def __init__(
        self,
        url: Union[str, None],
        proxies: Optional[
            Dict[str, str]
        ] = None,  # allows us to specify optional proxy server
        timeout: Optional[
            Union[float, Tuple[float, float], Tuple[float, None]]
        ] = None,  # allows us to specify optional timeout for request
        wild_mode: Optional[bool] = False,
        html: Union[str, bytes, None] = None,
    ):
        if html:
            self.page_data = html
            self.url = url
        else:
            assert url is not None, "url required for fetching recipe data"
            resp = requests.get(
                url,
                headers=HEADERS,
                proxies=proxies,
                timeout=timeout,
            )
            self.page_data = resp.content
            self.url = resp.url

        self.wild_mode = wild_mode
        self.soup = BeautifulSoup(self.page_data, "html.parser")
        self.schema = SchemaOrg(self.page_data)

        # Attach the plugins as instructed in settings.PLUGINS
        if not hasattr(self.__class__, "plugins_initialized"):
            for name, func in inspect.getmembers(self, inspect.ismethod):
                current_method = getattr(self.__class__, name)
                for plugin in reversed(settings.PLUGINS):
                    if plugin.should_run(self.host(), name):
                        current_method = plugin.run(current_method)
                setattr(self.__class__, name, current_method)
            setattr(self.__class__, "plugins_initialized", True)

    @classmethod
    def host(cls) -> str:
        """Return the host of website the scraper is for.
        This is used to match a webpage to the correct scraper.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def canonical_url(self):
        """Return the absolute canonical URL for the webpage being scraped.
        This is typically explicitly stated in the markup and may be different than the
        URL being scraped e.g. query parameters removed.

        If the webpage does not define a canonical URL, return the scraped URl.

        Returns
        -------
        str
            Canonical URL for webpage
        """
        canonical_link = self.soup.find("link", {"rel": "canonical", "href": True})
        if canonical_link:
            return urljoin(self.url, canonical_link["href"])
        return self.url

    def title(self) -> str:
        """Return the title of the recipe on the webpage.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def category(self) -> str:
        """Return the category of the recipe on the webpage.

        This value is often present in the recipe schema data, but not all websites
        provide it.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def total_time(self) -> int:
        """Return the total time it takes to prepare and cook the recipe, in minutes.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def cook_time(self) -> int:
        """Return the cook time of the recipe, in minutes.

        This value is often present in the recipe schema data, but not all websites
        provide it.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def prep_time(self) -> int:
        """Return the preparation time of the recipe, in minutes.

        This value is often present in the recipe schema data, but not all websites
        provide it.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def yields(self) -> str:
        """Return the number of servings or items for the recipe.
        This typically has the format "4 servings", "8 items" or "1 cake" etc.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def image(self) -> str:
        """Return the absolute URL of the photo of the recipe.

        This value is often present in the recipe schema data.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def nutrients(self) -> Dict[str, str]:
        """Return the a dictionary of nutrients for the recipe.
        The nutrients are per serving or item the recipe makes.

        This value is sometimes present in the recipe schema data. The inforamtion
        a recipe may provide about nutrients varies, so the returned dictionary does
        does not have a fixed set of keys.
        The value of each dictionary item should include the units.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def language(self) -> Optional[str]:
        """Return the human language the recipe is written in.

        This function may be overridden by the site specific scraper if this
        implementation does not provide the correct result.
        """
        candidate_languages: OrderedDict[str, bool] = OrderedDict()
        html = self.soup.find("html", {"lang": True})
        lang = html.get("lang")
        if not isinstance(lang, str):
            return None

        candidate_languages[lang] = True

        # Deprecated: check for a meta http-equiv header
        # See: https://www.w3.org/International/questions/qa-http-and-lang
        meta_language = self.soup.find(
            "meta",
            {
                "http-equiv": lambda x: x and x.lower() == "content-language",
                "content": True,
            },
        )
        if meta_language:
            language = meta_language.get("content").split(",", 1)[0]
            if language:
                candidate_languages[language] = True

        # If other languages exist, remove 'en' commonly generated by HTML editors
        if len(candidate_languages) > 1:
            candidate_languages.pop("en", None)

        # Return the first candidate language
        return candidate_languages.popitem(last=False)[0]

    def ingredients(self) -> List[str]:
        """Return the list of ingredients for the recipe. Each ingredient should be
        an element of the returned list.

        This function is implemented by the site specific scraper. The data can often be
        extracted from the recipe schema data.
        """
        raise NotImplementedError("This should be implemented.")

    def ingredient_groups(self) -> List[IngredientGroup]:
        """Return the list of ingredients grouped by subheading in the recipe.

        The default implementation returns a single group of ingredients where the
        purpose is None and the ingredients are the ingredients returned by the
        .ingredients() function.

        This function should be overridden by the site specific scraper for scrapers
        where the recipes may have grouped ingredients. Some utility functions that may
        be helpful are found in the _grouping_utils.py file.
        """
        return [IngredientGroup(purpose=None, ingredients=self.ingredients())]

    def instructions(self) -> str:
        """Return the instructions to prepare the recipe, as a single string.
        The individual steps on the instructions should be delimited by a "\n" character.

        This function is implemented by the site specific scraper. The data can often be
        extracted from the recipe schema data.
        """
        raise NotImplementedError("This should be implemented.")

    def instructions_list(self) -> List[str]:
        """Return the instructions to prepare the recipe, as a list of strings.
        Each element of the list is a step of the instructions.

        This default implementation is usually correct for most scrapers, if the format of
        .instructions() return is as described above.
        """
        return [
            instruction
            for instruction in self.instructions().split("\n")
            if instruction
        ]

    def ratings(self) -> float:
        """Return the rating of the recipe, as a decimal number.
        The number is typically based on a 5 star rating system.

        This value is often present in the recipe schema data.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def author(self) -> str:
        """Return the author of the recipe.

        This value is often present in the recipe schema data.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def cuisine(self) -> str:
        """Return the cuisine of the recipe.

        This value is often present in the recipe schema data.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def description(self) -> str:
        """Return the description of the recipe.

        This value is often present in the recipe schema data.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def reviews(self) -> List[Dict[str, str]]:
        """Return a list of reviews for the recipe.
        Each review should comprise a dictionary containing the review details.
        Suggested items are reviewer, date, rating, review body.

        This value is not present in the recipe schema data and must be extracted
        from the recipe html markup.

        This function is implemented by the site specific scraper.
        """
        raise NotImplementedError("This should be implemented.")

    def links(self) -> List[Dict[str, Any]]:
        """Return a list of all <a> tags found in the webpage.
        Each element of the list is a dictionary of the attributes of the <a> tag, where
        the keys are the attributes names and the values are the attributes values.

        In general, the only key guaranteed to exist is "href".
        """
        invalid_href = {"#", ""}
        links_html = self.soup.findAll("a", href=True)

        return [link.attrs for link in links_html if link["href"] not in invalid_href]

    def site_name(self):
        meta = self.soup.find("meta", property="og:site_name")
        return meta.get("content") if meta else None

    def to_json(self):
        """Return all the available scraped data as a JSON compatible dictionary.
        The keys of the dictionary are the names of all callable public functions
        implemented by the site specific scraper, with the exception of the
        .links(), .soup() and .to_json().
        """
        json_dict = {}
        public_method_names = [
            method
            for method in dir(self)
            if callable(getattr(self, method))
            if not method.startswith("_") and method not in ["soup", "links", "to_json"]
        ]
        for method in public_method_names:
            try:
                if method == "ingredient_groups":
                    json_dict[method] = [i.__dict__ for i in getattr(self, method)()]
                else:
                    json_dict[method] = getattr(self, method)()
            except Exception:
                pass
        return json_dict
