SUBDIRS = docs
PKGNAME = yum-utils
UTILS = package-cleanup debuginfo-install repoclosure repomanage repoquery repo-graph repo-rss yumdownloader yum-builddep repotrack reposync repodiff yum-debug-dump
UTILSROOT = yum-complete-transaction 
VERSION=$(shell awk '/Version:/ { print $$2 }' ${PKGNAME}.spec)
RELEASE=$(shell awk '/Release:/ { print $$2 }' ${PKGNAME}.spec)
WEBHOST = login.dulug.duke.edu
WEBPATH = /home/groups/yum/web/download/yum-utils/

clean:
	rm -f *.pyc *.pyo *~
	rm -f test/*~
	rm -f *.tar.gz

install:
	mkdir -p $(DESTDIR)/usr/bin/
	mkdir -p $(DESTDIR)/usr/sbin/
	mkdir -p $(DESTDIR)/usr/share/man/man1
	for util in $(UTILS); do \
		install -m 755 $$util.py $(DESTDIR)/usr/bin/$$util; \
	done
	for util in $(UTILSROOT); do \
		install -m 755 $$util.py $(DESTDIR)/usr/sbin/$$util; \
	done

	for d in $(SUBDIRS); do make DESTDIR=`cd $(DESTDIR); pwd` -C $$d install; [ $$? = 0 ] || exit 1; done

archive:
	@rm -rf ${PKGNAME}-${VERSION}.tar.gz
	@git-archive --format=tar --prefix=$(PKGNAME)-$(VERSION)/ HEAD | gzip -9v >${PKGNAME}-$(VERSION).tar.gz
	@echo "The archive is in ${PKGNAME}-$(VERSION).tar.gz"
	
srpm: archive
	rm -f ~/rpmbuild/SRPMS/${PKGNAME}-${VERSION}-*.src.rpm
	rpmbuild -ts  ${PKGNAME}-${VERSION}.tar.gz

release:
	@git commit -a -m "bumped yum-utils version to $(VERSION)"
	@$(MAKE) ChangeLog
	@git commit -a -m "updated ChangeLog"
	@git push
	@git tag -a -f -m "Tagged ${PKGNAME}-$(VERSION)" ${PKGNAME}-$(VERSION)
	@git push --tags origin
	@$(MAKE) upload

test-release:
	@git checkout -b release-test
	@cat yum-utils.spec | sed  's/^Version:.*/&.test/' > yum-utils-test.spec ; mv yum-utils-test.spec yum-utils.spec
	VERSION=$VERSION.test
	@git commit -a -m "bumped yum-utils version to $(VERSION)"
	@$(MAKE) ChangeLog
	@git commit -a -m "updated ChangeLog"
	@$(MAKE) archive
	@rpmbuild -ta  ${PKGNAME}-${VERSION}.tar.gz
	@git checkout -f
	@git checkout master
	@git branch -D release-test
	
upload: archive srpm
	@scp ${PKGNAME}-${VERSION}.tar.gz $(WEBHOST):$(WEBPATH)/
	@scp ~/rpmbuild/SRPMS/${PKGNAME}-${VERSION}-*.src.rpm $(WEBHOST):$(WEBPATH)/	
	@rm -rf ${PKGNAME}-${VERSION}.tar.gz
	
ChangeLog: FORCE
	@git log --pretty --numstat --summary | ./tools/git2cl > ChangeLog
	
	
FORCE:	
