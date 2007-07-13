INITD ?= /etc/rc.d/init.d

install:
	mkdir -p $(DESTDIR)/etc/sysconfig
	mkdir -p $(DESTDIR)$(INITD)
	install -m 644 yum-updateonboot.sysconfig $(DESTDIR)/etc/sysconfig/yum-updateonboot
	install -m 755 yum-updateonboot.init $(DESTDIR)$(INITD)/yum-updateonboot

