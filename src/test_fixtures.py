"""Test fixtures with anonymized mock content."""

# Mock weekly edition HTML with tech-themed content
MOCK_WEEKLY_EDITION_HTML = """
<!DOCTYPE html>
<html>
<head><title>TechWeekly - December 15, 2024</title></head>
<body>
    <img src="https://example.com/content/2024/12/20241215_DE_US.jpg" alt="Cover">

    <div class="section">
        <h2>This week in tech</h2>
        <a href="/2024/12/15/stay-hungry-stay-foolish">Stay Hungry, Stay Foolish: The Stanford Legacy</a>
        <a href="/2024/12/15/connecting-dots-backwards">Why you can only connect the dots looking backwards</a>
    </div>

    <div class="section">
        <h2>Leaders</h2>
        <a href="/2024/12/15/fast-inverse-square-root">The magic of 0x5f3759df: A computational miracle</a>
        <a href="/2024/12/15/moores-law-ending">Moore's Law isn't dead, it's just resting</a>
    </div>

    <div class="section">
        <h2>Science & technology</h2>
        <a href="/2024/12/15/quantum-supremacy-debate">The quantum supremacy debate heats up</a>
        <a href="/2024/12/15/ai-consciousness">Can machines think? The new Turing test</a>
    </div>

    <div class="section">
        <h2>Business</h2>
        <a href="/2024/12/15/unicorn-bubble">The one-person unicorn phenomenon</a>
        <a href="/2024/12/15/crypto-winter-thaw">Digital gold rush 2.0</a>
    </div>
</body>
</html>
"""

# Weekly edition snippet with short WTW anchor text (live Economist pattern)
MOCK_WEEKLY_EDITION_WTW_HTML = """
<!DOCTYPE html>
<html>
<body>
    <h2>The world this week</h2>
    <h3><a href="/the-world-this-week/2026/07/09/politics">Politics</a></h3>
    <h3><a href="/the-world-this-week/2026/07/09/business">Business</a></h3>
    <h3><a href="/the-world-this-week/2026/07/09/cartoon-test-slug">Cartoon: Test headline</a></h3>
    <a href="/interactive/middle-east-and-africa/2026/07/08/sample-photo-essay">Is this a photo essay with a long enough title</a>
</body>
</html>
"""

# Bespoke /interactive photo essay body layout
MOCK_ARTICLE_INTERACTIVE_HTML = """
<!DOCTYPE html>
<html>
<body>
    <main id="content">
        <h1>Photo essay headline</h1>
        <div class="article-text">
            <body-text>It was less a traditional lament for a slain leader than a victory parade across the region.</body-text>
        </div>
        <figure>
            <img src="/interactive/sample/processed-images/1424/sample.jpg"/>
            <figcaption><body-text>Mourners gather in the capital.</body-text></figcaption>
        </figure>
        <div class="article-text">
            <body-text>America carried out dozens of strikes overnight. Even so, diplomacy may still resume soon.</body-text>
        </div>
    </main>
</body>
</html>
"""

# Mock article HTML - Steve Jobs Stanford speech themed
MOCK_ARTICLE_JOBS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Stay Hungry, Stay Foolish: The Stanford Legacy</title>
    <meta property="og:image" content="https://example.com/hero_image.jpg">
    <link rel="preload" as="image" imagesrcset="https://example.com/hero_small.jpg 640w, https://example.com/hero_large.jpg 1424w">
</head>
<body>
    <h1>Stay Hungry, Stay Foolish: The Stanford Legacy</h1>
    <h2 class="e6h2z500">How three stories shaped a generation of entrepreneurs</h2>

    <div data-component="article-body">
        <p class="e1y9q0ei" data-component="paragraph">
            Lorem ipsum dolor sit amet, consectetur adipiscing elit. You can't connect the dots
            looking forward; you can only connect them looking backward. So you have to trust that
            the dots will somehow connect in your future. You have to trust in something — your gut,
            destiny, life, karma, whatever. This approach has never let me down, and it has made all
            the difference in my life.
        </p>

        <figure>
            <img src="https://example.com/dots_diagram.jpg" alt="Connecting dots">
            <figcaption>
                The famous dots metaphor visualized. Illustration: Lorem Ipsum Studios
            </figcaption>
        </figure>

        <p class="e1y9q0ei" data-component="paragraph">
            Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Sometimes life hits
            you in the head with a brick. Don't lose faith. I'm convinced that the only thing that
            kept me going was that I loved what I did. You've got to find what you love. And that is
            as true for your work as it is for your lovers.
        </p>

        <p class="e1y9q0ei" data-component="paragraph">
            Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris. Your work is going
            to fill a large part of your life, and the only way to be truly satisfied is to do what
            you believe is great work. And the only way to do great work is to love what you do.
            If you haven't found it yet, keep looking. Don't settle.
        </p>

        <p class="e1y9q0ei" data-component="paragraph">
            Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore.
            Remembering that you are going to die is the best way I know to avoid the trap of
            thinking you have something to lose. You are already naked. There is no reason not to
            follow your heart.
        </p>
    </div>
</body>
</html>
"""

MOCK_CARTOON_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Cartoon: Test headline</title>
    <meta property="og:image" content="https://example.com/cartoon_hero.png">
</head>
<body>
    <main id="content">
        <article>
            <h1>Cartoon: Test headline</h1>
            <h2>A lighter take on the news</h2>
            <figure>
                <img src="https://example.com/cartoon_hero.png" alt="Cartoon">
                <figcaption>Illustration: KAL</figcaption>
            </figure>
            <p class="e1y9q0ei" data-component="paragraph">
                Dig deeper into the subjects of this week's cartoon.
            </p>
        </article>
    </main>
</body>
</html>
"""

# Mock article HTML - Fast inverse square root
MOCK_ARTICLE_QUAKE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>The magic of 0x5f3759df: A computational miracle</title>
</head>
<body>
    <h1>The magic of 0x5f3759df: A computational miracle</h1>
    <p class="ykv9c9">How a mysterious constant revolutionized 3D graphics</p>

    <div itemprop="articleBody">
        <p class="1l5amll">
            Lorem ipsum dolor sit amet, the fast inverse square root algorithm is a method of
            computing x^(-1/2) using Newton's method with a clever initial guess. The algorithm was
            often misattributed to John Carmack, but actually originated earlier at Silicon Graphics.
        </p>

        <figure>
            <img src="https://example.com/quake_code.jpg" alt="The magical code">
            <figcaption>
                The legendary code snippet that baffled programmers for years.
                Photo: Quake III Arena source code
            </figcaption>
        </figure>

        <p class="1l5amll">
            Consectetur adipiscing elit, sed do eiusmod. The magic constant 0x5f3759df provides an
            extremely good first approximation using bit-level hacking. The code reads:
            <code>i = 0x5f3759df - (i >> 1); // what the fuck?</code>
            This comment has become legendary in programming circles.
        </p>

        <p class="1l5amll">
            Tempor incididunt ut labore et dolore magna aliqua. The algorithm was crucial for
            real-time 3D graphics when every CPU cycle counted. It computed the result about 4 times
            faster than the standard library function, enabling smooth gameplay in Quake III Arena.
        </p>

        <figure>
            <img src="https://example.com/performance_graph.jpg" alt="Performance comparison">
            <figcaption>
                Performance comparison: Fast inverse square root vs standard methods.
                Chart: Benchmark Labs 2024
            </figcaption>
        </figure>

        <p class="1l5amll">
            Ut enim ad minim veniam, quis nostrud exercitation. Modern CPUs have dedicated
            instructions for this operation, but the algorithm remains a masterpiece of optimization
            and a testament to the ingenuity of early game programmers.
        </p>
    </div>
</body>
</html>
"""

# Mock article with lorem ipsum content
MOCK_ARTICLE_LOREM_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Lorem Ipsum: A Deep Dive into Placeholder Text</title>
</head>
<body>
    <h1>Lorem Ipsum: A Deep Dive into Placeholder Text</h1>

    <section class="ei2yr3n0">
        <p class="e1y9q0ei">
            Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor
            incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud
            exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
        </p>

        <p class="e1y9q0ei">
            Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat
            nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui
            officia deserunt mollit anim id est laborum.
        </p>

        <figure>
            <img src="https://example.com/lorem_history.jpg" alt="History of Lorem Ipsum">
            <figcaption>The evolution of placeholder text through the ages</figcaption>
        </figure>

        <p class="e1y9q0ei">
            Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque
            laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi
            architecto beatae vitae dicta sunt explicabo.
        </p>
    </section>
</body>
</html>
"""

# Mock HTML with edge cases
MOCK_ARTICLE_EDGE_CASES_HTML = """
<!DOCTYPE html>
<html>
<head><title>Edge Cases Test</title></head>
<body>
    <h1>Testing <em>Edge</em> Cases</h1>

    <main role="main">
        <p class="e1y9q0ei">Short paragraph.</p>

        <p class="e1y9q0ei">
            This paragraph contains <strong>bold</strong>, <em>italic</em>, and
            <a href="https://example.com">links</a>. It also has <small>SMALL CAPS</small> text.
        </p>

        <p class="e1y9q0ei">
            Special symbols: TM becomes ™, (R) becomes ®, Copyright (C) becomes ©.
        </p>

        <!-- This should be filtered out -->
        <p class="e1y9q0ei">
            Sign up for our newsletter! Subscribe now to download the app. This article appeared
            in the print edition. Reuse this content freely.
        </p>

        <figure>
            <img src="javascript:alert('xss')">
        </figure>

        <figure>
            <img src="https://example.com/tracking.gif">
        </figure>

        <figure>
            <img src="https://example.com/20241215_DE_UK.jpg">
        </figure>

        <p class="e1y9q0ei">
            Lorem ipsum dolor sit amet, consectetur adipiscing elit. This is a normal paragraph
            that should be included in the output after filtering.
        </p>
    </main>
</body>
</html>
"""

# Test image URLs
TEST_IMAGE_URLS = [
    "https://example.com/test_image_1.jpg",
    "https://example.com/test_image_2.png",
    "https://example.com/cdn-cgi/image/width=640,quality=80,format=auto/content-assets/test.jpg",
]

# Test cover URL
TEST_COVER_URL = "https://example.com/content/2024/12/20241215_DE_US.jpg"
