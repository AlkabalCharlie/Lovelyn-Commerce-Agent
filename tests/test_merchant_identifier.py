from services.merchant_identifier import identify_merchant


def test_identifies_etsy():
    assert identify_merchant("https://www.etsy.com/listing/123456789/item") == "Etsy"


def test_identifies_jvzoo():
    assert identify_merchant("https://www.jvzoo.com/b/1234/5678") == "JVZoo"


def test_identifies_payhip():
    assert identify_merchant("https://payhip.com/b/Yzi3a") == "Payhip"


def test_identifies_ebay():
    assert identify_merchant("https://www.ebay.com/itm/123456") == "eBay"


def test_unknown_domain_is_independent():
    assert identify_merchant("https://randomstore.com/p/1") == "Independent / Other"