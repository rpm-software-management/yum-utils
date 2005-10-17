SUBDIRS = docs
PKGNAME = yum-utils
VERSION=$(shell awk '/Version:/ { print $$2 }' ${PKGNAME}.spec)
RELEASE=$(shell awk '/Release:/ { print $$2 }' ${PKGNAME}.spec)

clean:
	rm -f *.pyc *.pyo *~

install:
	mkdir -p $(DESTDIR)/usr/bin/
	install -m 755 package-cleanup.py $(DESTDIR)/usr/bin/package-cleanup
	install -m 755 repoclosure.py $(DESTDIR)/usr/bin/repoclosure
	install -m 755 repomanage.py $(DESTDIR)/usr/bin/repomanage
	install -m 755 repoquery.py $(DESTDIR)/usr/bin/repoquery
	install -m 755 repo-rss.py $(DESTDIR)/usr/bin/repo-rss
	install -m 755 yumdownloader.py $(DESTDIR)/usr/bin/yumdownloader
	install -m 755 yum-builddep.py $(DESTDIR)/usr/bin/yum-builddep

	for d in $(SUBDIRS); do make DESTDIR=`cd $(DESTDIR); pwd` -C $$d install; [ $$? = 0 ] || exit 1; done

archive:
	@rm -rf ${PKGNAME}-%{VERSION}.tar.gz
	@rm -rf /tmp/${PKGNAME}-$(VERSION) /tmp/${PKGNAME}
	@dir=$$PWD; cd /tmp; cp -a $$dir ${PKGNAME}
	@rm -f /tmp/${PKGNAME}/${PKGNAME}-daily.spec
	@mv /tmp/${PKGNAME} /tmp/${PKGNAME}-$(VERSION)
	@dir=$$PWD; cd /tmp; tar cvzf $$dir/${PKGNAME}-$(VERSION).tar.gz ${PKGNAME}-$(VERSION)
	@rm -rf /tmp/${PKGNAME}-$(VERSION)	
	@echo "The archive is in ${PKGNAME}-$(VERSION).tar.gz"

