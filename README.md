# The Bookfather

Full documentation (setup, data pipeline, database schema, API): [docs/index.md](docs/index.md)

# Features

## Data cleaning and alignment
Align the different sources of dataset, and create a unified sqlite DB schema.

## API services
Create CRUD API services to interact with the data.
- Search using string matching
- Similar books search if no string match

## Book recommendation
- new to books, here are the best 5 by genre
- read a few books? let us know and we'll recommend

## Agentic AI interface
- AI based contextual book search
- Use agentic memory to build user intent overtime based on their journey with books

## Learning from Experience
- Ask a question, and we'll recommend a book that may answer your question

# Dataset Resources

## Books Dataset 01
Kaggle dataset overview by authors: This dataset comprises information scraped from wonderbk.com, a popular online bookstore. The dataset contains details of 103,063 books, with key attributes such as title, authors, description, category, publisher, starting price, and publish date.

https://www.kaggle.com/datasets/elvinrustam/books-dataset


## Books Dataset 02
Overview by authors: Kaggle dataset overview by authors: This dataset has been compiled by Cai-Nicolas Ziegler in 2004, and it comprises of three tables for users, books and ratings. Explicit ratings are expressed on a scale from 1-10 (higher values denoting higher appreciation) and implicit rating is expressed by 0

https://www.kaggle.com/datasets/saurabhbagchi/books-dataset
http://www2.informatik.uni-freiburg.de/~cziegler/BX/


## Best Books Ever Dataset
The dataset has been collected in the frame of the Prac1 of the subject Tipology and Data Life Cycle of the Master's Degree in Data Science of the Universitat Oberta de Catalunya (UOC).

https://zenodo.org/records/4265096


## Goodreads Book Graph Datasets
Overview by authors: These datasets were collected in late 2017 from goodreads.com, where the authors only scraped users' public shelves, i.e. everyone can see it on web without login. User IDs and review IDs are anonymized. They collected these datasets for academic use only. (non-commercial purposes). They collected three groups of datasets: (1) meta-data of the books, (2) user-book interactions (users' public shelves) and (3) users' detailed book reviews. These datasets can be merged together by joining on book/user/review ids.

Basic Statistics of the Complete Book Graph:
- 2,360,655 books (1,521,962 works, 400,390 book series, 829,529 authors)
- 876,145 users; 228,648,342 user-book interactions in users' shelves (include 112,131,203 reads and 104,551,549 ratings)

https://cseweb.ucsd.edu/~jmcauley/datasets/goodreads.html


## Other sources

1. https://github.com/scostap/goodreads_bbe_dataset
2. https://zenodo.org/records/4265096
3. https://news.ycombinator.com/item?id=44252070

