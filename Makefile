SUBDIRS = docs
PKGNAME = yum-utils
UTILS = package-cleanup debuginfo-install repoclosure repomanage repoquery repo-graph repo-rss yumdownloader yum-builddep repotrack reposync repodiff yum-debug-dump verifytree yum-groups-manager
UTILSROOT = yum-complete-transaction 
VERSION=$(shell awk '/Version:/ { print $$2 }' ${PKGNAME}.spec)
RELEASE=$(shell awk -F%: '/Release:/ { print $$2 }' ${PKGNAME}.spec ')
SRPM_RELEASE=$(shell awk '/Release:/ { split($$2,a,"%"); print a[1] }' ${PKGNAME}.spec )
SRPM_FILE = ${PKGNAME}-${VERSION}-${SRPM_RELEASE}.src.rpm
WEBHOST = login.dulug.duke.edu
WEBPATH = /home/groups/yum/web/download/yum-utils/

NMPROG=yum-NetworkManager-dispatcher
NMPATH=$(DESTDIR)/etc/NetworkManager/dispatcher.d

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
	mkdir -p $(NMPATH)
	install -m 755 $(NMPROG) $(NMPATH)

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
	@git tag -s -f -m "Tagged ${PKGNAME}-$(VERSION)" ${PKGNAME}-$(VERSION)
	@git push --tags origin
	@$(MAKE) upload

test-release:
	@git checkout -b release-test
	# Add '.test' to Version in spec file
	@cat yum-utils.spec | sed  's/^Version:.*/&.test/' > yum-utils-test.spec ; mv yum-utils-test.spec yum-utils.spec
	@git commit -a -m "bumped yum-utils version to $(VERSION).test"
	# Make Changelog
	@git log --pretty --numstat --summary | ./tools/git2cl > ChangeLog
	@git commit -a -m "updated ChangeLog"
    # Make archive
	@rm -rf ${PKGNAME}-${VERSION}.test.tar.gz
	@git-archive --format=tar --prefix=$(PKGNAME)-$(VERSION).test/ HEAD | gzip -9v >${PKGNAME}-$(VERSION).test.tar.gz
	# Build RPMS
	@rpmbuild -ta  ${PKGNAME}-${VERSION}.test.tar.gz
	@$(MAKE) test-cleanup
    

test-cleanup:	
	@rm -rf ${PKGNAME}-${VERSION}.test.tar.gz
	@echo "Cleanup the git release-test local branch"
	@git checkout -f
	@git checkout master
	@git branch -D release-test
    
upload: archive srpm
	@scp ${PKGNAME}-${VERSION}.tar.gz $(WEBHOST):$(WEBPATH)/
	@scp ~/rpmbuild/SRPMS/${PKGNAME}-${VERSION}-*.src.rpm $(WEBHOST):$(WEBPATH)/${SRPM_FILE}
	@rm -rf ${PKGNAME}-${VERSION}.tar.gz
	
ChangeLog: FORCE
	@git log --pretty --numstat --summary | ./tools/git2cl > ChangeLog

pylint:
	@pylint --rcfile=test/yum-utils-pylintrc \
		yumdownloader.py yum-complete-transaction.py yum-debug-dump.py yum-builddep.py \
                debuginfo-install.py
	
FORCE:	
