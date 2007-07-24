SUBDIRS = docs
PKGNAME = yum-utils
UTILS = package-cleanup debuginfo-install repoclosure repomanage repoquery repo-graph repo-rss yumdownloader yum-builddep repotrack reposync
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
	mkdir -p $(DESTDIR)/usr/share/man/man1
	for util in $(UTILS); do \
		install -m 755 $$util.py $(DESTDIR)/usr/bin/$$util; \
	done

	for d in $(SUBDIRS); do make DESTDIR=`cd $(DESTDIR); pwd` -C $$d install; [ $$? = 0 ] || exit 1; done

archive:
	@rm -rf ${PKGNAME}-${VERSION}.tar.gz
	@rm -rf /tmp/${PKGNAME}-$(VERSION) /tmp/${PKGNAME}
	@dir=$$PWD; cd /tmp; cp -a $$dir ${PKGNAME}
	@rm -f /tmp/${PKGNAME}/${PKGNAME}-daily.spec
	@mv /tmp/${PKGNAME} /tmp/${PKGNAME}-$(VERSION)
	@rm -rf /tmp/${PKGNAME}-$(VERSION)/.git
	@rm -rf /tmp/${PKGNAME}-$(VERSION)/tools	
	@dir=$$PWD; cd /tmp; tar cvzf $$dir/${PKGNAME}-$(VERSION).tar.gz ${PKGNAME}-$(VERSION)
	@rm -rf /tmp/${PKGNAME}-$(VERSION)	
	@echo "The archive is in ${PKGNAME}-$(VERSION).tar.gz"
	
srpm: archive
	rm -f ~/rpmbuild/SRPMS/${PKGNAME}-${VERSION}-*.src.rpm
	rpmbuild -ts  ${PKGNAME}-${VERSION}.tar.gz

release:
	@git commit -a -m "bumped yum-utils version to $(VERSION)"
	@$(MAKE) ChangeLog
	@git commit -a -m "updated ChangeLog"
	@git tag -a ${PKGNAME}-$(VERSION) -m "Tagged ${PKGNAME}-$(VERSION)"
	@git push --tags
	@$(MAKE) upload
	
upload: archive srpm
	@scp ${PKGNAME}-${VERSION}.tar.gz $(WEBHOST):$(WEBPATH)/
	@scp ~/rpmbuild/SRPMS/${PKGNAME}-${VERSION}-*.src.rpm $(WEBHOST):$(WEBPATH)/	
	@rm -rf ${PKGNAME}-${VERSION}.tar.gz
	
ChangeLog: FORCE
	@git log --pretty --numstat --summary | ./tools/git2cl > ChangeLog
	
	
FORCE:	
