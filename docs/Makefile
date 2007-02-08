DOCS = repoquery package-cleanup repo-rss yumdownloader yum-builddep yum-changelog
DOCS5 = yum-changelog.conf

all:
	echo "Nothing to do"

clean:
	rm -f *.pyc *.pyo *~

install:
	mkdir -p $(DESTDIR)/usr/share/man/man1
	mkdir -p $(DESTDIR)/usr/share/man/man5
	for doc in $(DOCS); do \
		install -m 644 $$doc.1 $(DESTDIR)/usr/share/man/man1/; \
	done
	for doc in $(DOCS5); do \
		install -m 644 $$doc.5 $(DESTDIR)/usr/share/man/man5/; \
	done
	