/* Adapted from
 * https://github.com/linux-rdma/rdma-core/blob/v42.7/ccan/str.h

 * Statement of Purpose
 * 
 * The laws of most jurisdictions throughout the world automatically confer
 * exclusive Copyright and Related Rights (defined below) upon the creator and
 * subsequent owner(s) (each and all, an "owner") of an original work of
 * authorship and/or a database (each, a "Work").
 * 
 * Certain owners wish to permanently relinquish those rights to a Work for the
 * purpose of contributing to a commons of creative, cultural and scientific works
 * ("Commons") that the public can reliably and without fear of later claims of
 * infringement build upon, modify, incorporate in other works, reuse and
 * redistribute as freely as possible in any form whatsoever and for any purposes,
 * including without limitation commercial purposes. These owners may contribute
 * to the Commons to promote the ideal of a free culture and the further
 * production of creative, cultural and scientific works, or to gain reputation or
 * greater distribution for their Work in part through the use and efforts of
 * others.
 * 
 * For these and/or other purposes and motivations, and without any expectation of
 * additional consideration or compensation, the person associating CC0 with a
 * Work (the "Affirmer"), to the extent that he or she is an owner of Copyright
 * and Related Rights in the Work, voluntarily elects to apply CC0 to the Work and
 * publicly distribute the Work under its terms, with knowledge of his or her
 * Copyright and Related Rights in the Work and the meaning and intended legal
 * effect of CC0 on those rights.
 * 
 * 1. Copyright and Related Rights. A Work made available under CC0 may be
 * protected by copyright and related or neighboring rights ("Copyright and
 * Related Rights"). Copyright and Related Rights include, but are not limited to,
 * the following:
 * 
 *     the right to reproduce, adapt, distribute, perform, display, communicate,
 * and translate a Work; moral rights retained by the original author(s) and/or
 * performer(s); publicity and privacy rights pertaining to a person's image or
 * likeness depicted in a Work; rights protecting against unfair competition in
 * regards to a Work, subject to the limitations in paragraph 4(a), below; rights
 * protecting the extraction, dissemination, use and reuse of data in a Work;
 * database rights (such as those arising under Directive 96/9/EC of the European
 * Parliament and of the Council of 11 March 1996 on the legal protection of
 * databases, and under any national implementation thereof, including any amended
 * or successor version of such directive); and other similar, equivalent or
 * corresponding rights throughout the world based on applicable law or treaty,
 * and any national implementations thereof.
 * 
 * 2. Waiver. To the greatest extent permitted by, but not in contravention of,
 * applicable law, Affirmer hereby overtly, fully, permanently, irrevocably and
 * unconditionally waives, abandons, and surrenders all of Affirmer's Copyright
 * and Related Rights and associated claims and causes of action, whether now
 * known or unknown (including existing as well as future claims and causes of
 * action), in the Work (i) in all territories worldwide, (ii) for the maximum
 * duration provided by applicable law or treaty (including future time
 * extensions), (iii) in any current or future medium and for any number of
 * copies, and (iv) for any purpose whatsoever, including without limitation
 * commercial, advertising or promotional purposes (the "Waiver"). Affirmer makes
 * the Waiver for the benefit of each member of the public at large and to the
 * detriment of Affirmer's heirs and successors, fully intending that such Waiver
 * shall not be subject to revocation, rescission, cancellation, termination, or
 * any other legal or equitable action to disrupt the quiet enjoyment of the Work
 * by the public as contemplated by Affirmer's express Statement of Purpose.
 * 
 * 3. Public License Fallback. Should any part of the Waiver for any reason be
 * judged legally invalid or ineffective under applicable law, then the Waiver
 * shall be preserved to the maximum extent permitted taking into account
 * Affirmer's express Statement of Purpose. In addition, to the extent the Waiver
 * is so judged Affirmer hereby grants to each affected person a royalty-free, non
 * transferable, non sublicensable, non exclusive, irrevocable and unconditional
 * license to exercise Affirmer's Copyright and Related Rights in the Work (i) in
 * all territories worldwide, (ii) for the maximum duration provided by applicable
 * law or treaty (including future time extensions), (iii) in any current or
 * future medium and for any number of copies, and (iv) for any purpose
 * whatsoever, including without limitation commercial, advertising or promotional
 * purposes (the "License"). The License shall be deemed effective as of the date
 * CC0 was applied by Affirmer to the Work. Should any part of the License for any
 * reason be judged legally invalid or ineffective under applicable law, such
 * partial invalidity or ineffectiveness shall not invalidate the remainder of the
 * License, and in such case Affirmer hereby affirms that he or she will not (i)
 * exercise any of his or her remaining Copyright and Related Rights in the Work
 * or (ii) assert any associated claims and causes of action with respect to the
 * Work, in either case contrary to Affirmer's express Statement of Purpose.
 * 
 * 4. Limitations and Disclaimers.
 * 
 *     No trademark or patent rights held by Affirmer are waived, abandoned,
 * surrendered, licensed or otherwise affected by this document.  Affirmer offers
 * the Work as-is and makes no representations or warranties of any kind
 * concerning the Work, express, implied, statutory or otherwise, including
 * without limitation warranties of title, merchantability, fitness for a
 * particular purpose, non infringement, or the absence of latent or other
 * defects, accuracy, or the present or absence of errors, whether or not
 * discoverable, all to the greatest extent permissible under applicable law.
 * Affirmer disclaims responsibility for clearing rights of other persons that may
 * apply to the Work or any use thereof, including without limitation any person's
 * Copyright and Related Rights in the Work. Further, Affirmer disclaims
 * responsibility for obtaining any necessary consents, permissions or other
 * rights required for any use of the Work.  Affirmer understands and acknowledges
 * that Creative Commons is not a party to this document and has no duty or
 * obligation with respect to this CC0 or use of the Work.
 */

 #ifndef CCAN_STR_H
#define CCAN_STR_H
#include "config.h"
#include <string.h>
#include <stdbool.h>
#include <limits.h>
#include <ctype.h>

/**
 * streq - Are two strings equal?
 * @a: first string
 * @b: first string
 *
 * This macro is arguably more readable than "!strcmp(a, b)".
 *
 * Example:
 *	if (streq(somestring, ""))
 *		printf("String is empty!\n");
 */
#define streq(a,b) (strcmp((a),(b)) == 0)

/**
 * strstarts - Does this string start with this prefix?
 * @str: string to test
 * @prefix: prefix to look for at start of str
 *
 * Example:
 *	if (strstarts(somestring, "foo"))
 *		printf("String %s begins with 'foo'!\n", somestring);
 */
#define strstarts(str,prefix) (strncmp((str),(prefix),strlen(prefix)) == 0)

/**
 * strends - Does this string end with this postfix?
 * @str: string to test
 * @postfix: postfix to look for at end of str
 *
 * Example:
 *	if (strends(somestring, "foo"))
 *		printf("String %s end with 'foo'!\n", somestring);
 */
static inline bool strends(const char *str, const char *postfix)
{
	if (strlen(str) < strlen(postfix))
		return false;

	return streq(str + strlen(str) - strlen(postfix), postfix);
}

/**
 * stringify - Turn expression into a string literal
 * @expr: any C expression
 *
 * Example:
 *	#define PRINT_COND_IF_FALSE(cond) \
 *		((cond) || printf("%s is false!", stringify(cond)))
 */
#define stringify(expr)		stringify_1(expr)
/* Double-indirection required to stringify expansions */
#define stringify_1(expr)	#expr

/**
 * strcount - Count number of (non-overlapping) occurrences of a substring.
 * @haystack: a C string
 * @needle: a substring
 *
 * Example:
 *      assert(strcount("aaa aaa", "a") == 6);
 *      assert(strcount("aaa aaa", "ab") == 0);
 *      assert(strcount("aaa aaa", "aa") == 2);
 */
size_t strcount(const char *haystack, const char *needle);

/**
 * STR_MAX_CHARS - Maximum possible size of numeric string for this type.
 * @type_or_expr: a pointer or integer type or expression.
 *
 * This provides enough space for a nul-terminated string which represents the
 * largest possible value for the type or expression.
 *
 * Note: The implementation adds extra space so hex values or negative
 * values will fit (eg. sprintf(... "%p"). )
 *
 * Example:
 *	char str[STR_MAX_CHARS(int)];
 *
 *	sprintf(str, "%i", 7);
 */
#define STR_MAX_CHARS(type_or_expr)				\
	((sizeof(type_or_expr) * CHAR_BIT + 8) / 9 * 3 + 2	\
	 + STR_MAX_CHARS_TCHECK_(type_or_expr))

#if HAVE_TYPEOF
/* Only a simple type can have 0 assigned, so test that. */
#define STR_MAX_CHARS_TCHECK_(type_or_expr)		\
	({ typeof(type_or_expr) x = 0; (void)x; 0; })
#else
#define STR_MAX_CHARS_TCHECK_(type_or_expr) 0
#endif

/**
 * cisalnum - isalnum() which takes a char (and doesn't accept EOF)
 * @c: a character
 *
 * Surprisingly, the standard ctype.h isalnum() takes an int, which
 * must have the value of EOF (-1) or an unsigned char.  This variant
 * takes a real char, and doesn't accept EOF.
 */
static inline bool cisalnum(char c)
{
	return isalnum((unsigned char)c);
}
static inline bool cisalpha(char c)
{
	return isalpha((unsigned char)c);
}
static inline bool cisascii(char c)
{
	return isascii((unsigned char)c);
}
#if HAVE_ISBLANK
static inline bool cisblank(char c)
{
	return isblank((unsigned char)c);
}
#endif
static inline bool ciscntrl(char c)
{
	return iscntrl((unsigned char)c);
}
static inline bool cisdigit(char c)
{
	return isdigit((unsigned char)c);
}
static inline bool cisgraph(char c)
{
	return isgraph((unsigned char)c);
}
static inline bool cislower(char c)
{
	return islower((unsigned char)c);
}
static inline bool cisprint(char c)
{
	return isprint((unsigned char)c);
}
static inline bool cispunct(char c)
{
	return ispunct((unsigned char)c);
}
static inline bool cisspace(char c)
{
	return isspace((unsigned char)c);
}
static inline bool cisupper(char c)
{
	return isupper((unsigned char)c);
}
static inline bool cisxdigit(char c)
{
	return isxdigit((unsigned char)c);
}

#include <ccan/str_debug.h>

/* These checks force things out of line, hence they are under DEBUG. */
#ifdef CCAN_STR_DEBUG
#include <ccan/build_assert.h>

/* These are commonly misused: they take -1 or an *unsigned* char value. */
#undef isalnum
#undef isalpha
#undef isascii
#undef isblank
#undef iscntrl
#undef isdigit
#undef isgraph
#undef islower
#undef isprint
#undef ispunct
#undef isspace
#undef isupper
#undef isxdigit

/* You can use a char if char is unsigned. */
#if HAVE_BUILTIN_TYPES_COMPATIBLE_P && HAVE_TYPEOF
#define str_check_arg_(i)						\
	((i) + BUILD_ASSERT_OR_ZERO(!__builtin_types_compatible_p(typeof(i), \
								  char)	\
				    || (char)255 > 0))
#else
#define str_check_arg_(i) (i)
#endif

#define isalnum(i) str_isalnum(str_check_arg_(i))
#define isalpha(i) str_isalpha(str_check_arg_(i))
#define isascii(i) str_isascii(str_check_arg_(i))
#if HAVE_ISBLANK
#define isblank(i) str_isblank(str_check_arg_(i))
#endif
#define iscntrl(i) str_iscntrl(str_check_arg_(i))
#define isdigit(i) str_isdigit(str_check_arg_(i))
#define isgraph(i) str_isgraph(str_check_arg_(i))
#define islower(i) str_islower(str_check_arg_(i))
#define isprint(i) str_isprint(str_check_arg_(i))
#define ispunct(i) str_ispunct(str_check_arg_(i))
#define isspace(i) str_isspace(str_check_arg_(i))
#define isupper(i) str_isupper(str_check_arg_(i))
#define isxdigit(i) str_isxdigit(str_check_arg_(i))

#if HAVE_TYPEOF
/* With GNU magic, we can make const-respecting standard string functions. */
#undef strstr
#undef strchr
#undef strrchr

/* + 0 is needed to decay array into pointer. */
#define strstr(haystack, needle)					\
	((typeof((haystack) + 0))str_strstr((haystack), (needle)))
#define strchr(haystack, c)					\
	((typeof((haystack) + 0))str_strchr((haystack), (c)))
#define strrchr(haystack, c)					\
	((typeof((haystack) + 0))str_strrchr((haystack), (c)))
#endif
#endif /* CCAN_STR_DEBUG */

#endif /* CCAN_STR_H */
