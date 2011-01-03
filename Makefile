SUBDIRS = docs po yumutils
PKGNAME = yum-utils
UTILS = package-cleanup debuginfo-install repoclosure repomanage repoquery repo-graph repo-rss yumdownloader yum-builddep repotrack reposync repodiff yum-debug-dump yum-debug-restore verifytree yum-groups-manager find-repos-of-install needs-restarting yum-config-manager show-installed
UTILSROOT = yum-complete-transaction yumdb
VERSION=$(shell awk '/Version:/ { print $$2 }' ${PKGNAME}.spec)
RELEASE=$(shell awk -F%: '/Release:/ { print $$2 }' ${PKGNAME}.spec ')
SRPM_RELEASE=$(shell awk '/Release:/ { split($$2,a,"%"); print a[1] }' ${PKGNAME}.spec )
SRPM_FILE = ${PKGNAME}-${VERSION}-${SRPM_RELEASE}.src.rpm
WEBHOST = yum.baseurl.org
WEBPATH = /srv/projects/yum/web/download/yum-utils/
PY_FILES =  $(wildcard *.py) $(wildcard plugins/*/*.py) $(wildcard plugins/*/*/*.py)

NMPROG=yum-NetworkManager-dispatcher
NMPATH=$(DESTDIR)/etc/NetworkManager/dispatcher.d

BASHCOMP=yum-utils.bash
BASHCOMPPATH=$(DESTDIR)/etc/bash_completion.d

GITDATE=git$(shell date +%Y%m%d)
VER_REGEX=\(^Version:\s*[0-9]*\.[0-9]*\.\)\(.*\)
BUMPED_MINOR=${shell VN=`cat ${PKGNAME}.spec | grep Version| sed  's/${VER_REGEX}/\2/'`; echo $$(($$VN + 1))}
NEW_VER=${shell cat ${PKGNAME}.spec | grep Version| sed  's/\(^Version:\s*\)\([0-9]*\.[0-9]*\.\)\(.*\)/\2${BUMPED_MINOR}/'}
NEW_REL=0.1.${GITDATE}


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
	mkdir -p $(BASHCOMPPATH)
	install -m 644 $(BASHCOMP) $(BASHCOMPPATH)

archive:
	@rm -rf ${PKGNAME}-${VERSION}.tar.gz
	@git archive --format=tar --prefix=$(PKGNAME)-$(VERSION)/ HEAD | gzip -9v >${PKGNAME}-$(VERSION).tar.gz
	@echo "The archive is in ${PKGNAME}-$(VERSION).tar.gz"

srpm: archive
	rm -f ~/rpmbuild/SRPMS/${PKGNAME}-${VERSION}-*.src.rpm
	rpmbuild -ts  ${PKGNAME}-${VERSION}.tar.gz

release:
	@git commit -a -m "bumped yum-utils version to $(VERSION)"
	@$(MAKE) ChangeLog
	@git commit -a -m "updated ChangeLog"
	@git push
	@$(MAKE) release-tag
	@$(MAKE) upload

release-tag:
	@git tag -s -f -m "Tagged ${PKGNAME}-$(VERSION)" ${PKGNAME}-$(VERSION)
	@git push --tags origin

install-builddeps:
	su -c "yum install perl-TimeDate python-devel gettext intltool rpmdevtools"
	
test-release:
	@git checkout -b release-test
	# +1 Minor version and add 0.1-gitYYYYMMDD release
	@cat ${PKGNAME}.spec | sed  -e 's/${VER_REGEX}/\1${BUMPED_MINOR}/' -e 's/\(^Release:\s*\)\([0-9]*\)\(.*\)./\10.1.${GITDATE}%{?dist}/' > ${PKGNAME}-test.spec ; mv ${PKGNAME}-test.spec ${PKGNAME}.spec
	@git commit -a -m "bumped ${PKGNAME} version ${NEW_VER}-${NEW_REL}"
	# Make Changelog
	@git log --pretty --numstat --summary | ./tools/git2cl > ChangeLog
	@git commit -a -m "updated ChangeLog"
    	# Make archive
	@rm -rf ${PKGNAME}-${NEW_VER}.tar.gz
	@git archive --format=tar --prefix=$(PKGNAME)-$(NEW_VER)/ HEAD | gzip -9v >${PKGNAME}-$(NEW_VER).tar.gz
	# Build RPMS
	@rpmbuild -ta ${PKGNAME}-${NEW_VER}.tar.gz
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
	@pylint --rcfile=test/yum-utils-pylintrc $(PY_FILES) 2>/dev/null

pylint-short:
	@pylint -r n --rcfile=test/yum-utils-pylintrc $(PY_FILES) 2>/dev/null

FORCE:
