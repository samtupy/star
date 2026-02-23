# macsay

This provider exposes any voice available on a MacOS computer via the say command line utility that Apple provides.

It can be best to run this provider through a local terminal rather than ssh, as some voices have been known to be disfunctional otherwise.

The rate setting does work and is in words per minute.

To change the pitch, you should use the ```[[pbas xxx]]]``` speech tag anywhere in your text string.

If you wish for your personal voices to appear, you must examine and use the macpersonal_permission.m file included in this directory.
