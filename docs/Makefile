DOCS = repoquery package-cleanup repo-rss yumdownloader yum-builddep yum-changelog reposync \
       yum-list-data yum-filter-data yum-verify yum-utils yum-aliases yum-debug-dump yum-versionlock \
       yum-groups-manager debuginfo-install repodiff yum-fs-snapshot \
       show-installed show-changed-rco yum-debug-restore \
       find-repos-of-install needs-restarting repo-graph repoclosure \
       repomanage repotrack verifytree yum-config-manager
DOCS5 = yum-changelog.conf yum-versionlock.conf yum-fs-snapshot.conf
DOCS8 = yum-security yum-complete-transaction yumdb

all:
	echo "Nothing to do"

clean:
	rm -f *.pyc *.pyo *~

install:
	mkdir -p $(DESTDIR)/usr/share/man/man1
	mkdir -p $(DESTDIR)/usr/share/man/man5
	mkdir -p $(DESTDIR)/usr/share/man/man8
	for doc in $(DOCS); do \
		install -m 644 $$doc.1 $(DESTDIR)/usr/share/man/man1/; \
	done
	for doc in $(DOCS5); do \
		install -m 644 $$doc.5 $(DESTDIR)/usr/share/man/man5/; \
	done
	for doc in $(DOCS8); do \
		install -m 644 $$doc.8 $(DESTDIR)/usr/share/man/man8/; \
	done

